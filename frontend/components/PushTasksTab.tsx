"use client";

/**
 * PushTasksTab —— 机器人页「推送任务」Tab（W4 4.1 / 4.3）。
 *
 * 功能：任务列表（分页 + 状态过滤）、创建/编辑表单（含 CronEditor 4.2）、
 * 行操作（立即执行/暂停恢复/删除，均带确认）、任务日志弹窗（按 push_task_id
 * 过滤投递记录，复用页面既有日志样式）。
 *
 * 表格/徽章/弹窗沿用 app/bots/page.tsx 既有写法；确认交互与渠道删除一致
 * （原生 confirm），不引入新 UI 库。
 */

import { useCallback, useEffect, useState } from "react";
import {
  createPushTask,
  deletePushTask,
  listChannels,
  listPushLogs,
  listPushTasks,
  runPushTaskNow,
  updatePushTask,
  type BotChannel,
  type PushLog,
  type PushTask,
} from "@/lib/api/bots";
import CronEditor from "@/components/CronEditor";
import { describeCron } from "@/lib/cron";

const TRIGGER_LABELS: Record<string, string> = {
  cron: "定时",
  event: "事件",
  manual: "手动",
};

const EVENT_LABELS: Record<string, string> = {
  new_article: "新文章入库",
  hot_topic_update: "热点更新",
  daily_report: "日报发布",
};

const TASK_STATUS_LABELS: Record<string, string> = {
  active: "进行中",
  paused: "已暂停",
};

const TEMPLATE_PLACEHOLDER =
  "支持变量：{date} {time} {space_name} {doc_title} {hot_topic} {topic_count}";

interface Props {
  /** 当前会话用户 sub，作为任务创建者透传（未登录传空串走后端默认） */
  userSub: string;
}

interface TaskFormState {
  name: string;
  bot_channel_id: string;
  trigger_type: string;
  cron_expr: string;
  trigger_event: string;
  content_template: string;
}

const EMPTY_FORM: TaskFormState = {
  name: "",
  bot_channel_id: "",
  trigger_type: "cron",
  cron_expr: "10:00",
  trigger_event: "new_article",
  content_template: "",
};

export default function PushTasksTab({ userSub }: Props) {
  const [tasks, setTasks] = useState<PushTask[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [channels, setChannels] = useState<BotChannel[]>([]);

  // 创建/编辑弹窗
  const [showForm, setShowForm] = useState(false);
  const [editingTask, setEditingTask] = useState<PushTask | null>(null);
  const [form, setForm] = useState<TaskFormState>(EMPTY_FORM);
  const [formError, setFormError] = useState("");
  const [formLoading, setFormLoading] = useState(false);

  // 任务日志弹窗（4.3）
  const [logsTask, setLogsTask] = useState<PushTask | null>(null);
  const [logs, setLogs] = useState<PushLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  const channelName = useCallback(
    (id: string) => channels.find((c) => c.id === id)?.name || id,
    [channels],
  );

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await listPushTasks({
        status: statusFilter || undefined,
        page,
        page_size: 20,
      });
      setTasks(res.items || []);
      setTotal(res.total || 0);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载推送任务失败");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  useEffect(() => {
    listChannels({ status: "active", page: 1, page_size: 100 })
      .then((res) => setChannels(res.items || []))
      .catch(() => {});
  }, []);

  const openCreate = () => {
    setEditingTask(null);
    setForm({ ...EMPTY_FORM, bot_channel_id: channels[0]?.id || "" });
    setFormError("");
    setShowForm(true);
  };

  const openEdit = (t: PushTask) => {
    setEditingTask(t);
    setForm({
      name: t.name,
      bot_channel_id: t.bot_channel_id,
      trigger_type: t.trigger_type,
      cron_expr: t.cron_expr || "10:00",
      trigger_event: t.trigger_event || "new_article",
      content_template: t.content_template || "",
    });
    setFormError("");
    setShowForm(true);
  };

  const handleSubmit = async () => {
    setFormError("");
    if (!form.name.trim()) {
      setFormError("任务名称不能为空");
      return;
    }
    if (!form.bot_channel_id) {
      setFormError("请选择目标渠道");
      return;
    }
    setFormLoading(true);
    try {
      if (editingTask) {
        // 4.1c 编辑走 W1 并行交付的 PUT 端点；cron 非法时服务端 400 的
        // message 经 ApiError 透出，落在 formError 展示。
        await updatePushTask(editingTask.id, {
          name: form.name,
          cron_expr: form.trigger_type === "cron" ? form.cron_expr : "",
          trigger_event: form.trigger_type === "event" ? form.trigger_event : "",
          content_template: form.content_template,
        });
      } else {
        await createPushTask({
          name: form.name,
          bot_channel_id: form.bot_channel_id,
          trigger_type: form.trigger_type,
          cron_expr: form.trigger_type === "cron" ? form.cron_expr : "",
          trigger_event: form.trigger_type === "event" ? form.trigger_event : "",
          content_template: form.content_template,
          created_by: userSub || undefined,
        });
      }
      setShowForm(false);
      fetchTasks();
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setFormLoading(false);
    }
  };

  const handleRunNow = async (t: PushTask) => {
    if (!confirm(`确定立即执行任务「${t.name}」？将真实向渠道「${channelName(t.bot_channel_id)}」投递。`)) {
      return;
    }
    setError("");
    try {
      const res = await runPushTaskNow(t.id);
      setNotice(
        res.delivered
          ? `✅「${t.name}」已投递成功`
          : `❌「${t.name}」投递失败：${res.reason}`,
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "执行失败");
    }
  };

  const handleToggleStatus = async (t: PushTask) => {
    const next = t.status === "active" ? "paused" : "active";
    if (!confirm(`确定${next === "paused" ? "暂停" : "恢复"}任务「${t.name}」？`)) return;
    setError("");
    try {
      await updatePushTask(t.id, { status: next });
      fetchTasks();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "状态切换失败");
    }
  };

  const handleDelete = async (t: PushTask) => {
    if (!confirm(`确定删除任务「${t.name}」？此操作不可撤销。`)) return;
    setError("");
    try {
      await deletePushTask(t.id);
      fetchTasks();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const openLogs = async (t: PushTask) => {
    setLogsTask(t);
    setLogsLoading(true);
    try {
      // 后端按渠道维度出日志，任务维度在前端按 push_task_id 过滤
      const res = await listPushLogs(t.bot_channel_id, { page: 1, page_size: 50 });
      setLogs((res.items || []).filter((l) => l.push_task_id === t.id));
    } catch {
      setLogs([]);
    } finally {
      setLogsLoading(false);
    }
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">状态：</span>
          {[
            ["", "全部"],
            ["active", "进行中"],
            ["paused", "已暂停"],
          ].map(([value, label]) => (
            <button
              key={value || "all"}
              onClick={() => {
                setStatusFilter(value);
                setPage(1);
              }}
              className={`rounded px-3 py-1 text-sm ${
                statusFilter === value
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          onClick={openCreate}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          + 新建任务
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {notice && (
        <div className="mb-4 rounded border border-blue-300 bg-blue-50 p-3 text-sm text-blue-700">
          {notice}
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-gray-500">加载中...</div>
      ) : tasks.length === 0 ? (
        <div className="py-12 text-center text-gray-500">
          暂无推送任务，点击「新建任务」创建第一个定时/事件推送任务。
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg ring-1 ring-gray-200">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">任务名称</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">目标渠道</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">触发方式</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">状态</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">上次执行</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {tasks.map((t) => (
                <tr key={t.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">{t.name}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">{channelName(t.bot_channel_id)}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {TRIGGER_LABELS[t.trigger_type] || t.trigger_type}
                    {t.trigger_type === "cron" && t.cron_expr && (
                      <span className="ml-1 text-xs text-gray-400">{describeCron(t.cron_expr)}</span>
                    )}
                    {t.trigger_type === "event" && t.trigger_event && (
                      <span className="ml-1 text-xs text-gray-400">
                        {EVENT_LABELS[t.trigger_event] || t.trigger_event}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded px-2 py-0.5 text-xs ${
                        t.status === "active"
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {TASK_STATUS_LABELS[t.status] || t.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {t.last_run_at ? t.last_run_at.slice(0, 19).replace("T", " ") : "—"}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleRunNow(t)}
                        className="text-blue-600 hover:text-blue-800"
                      >
                        立即执行
                      </button>
                      <button
                        onClick={() => handleToggleStatus(t)}
                        className="text-blue-600 hover:text-blue-800"
                      >
                        {t.status === "active" ? "暂停" : "恢复"}
                      </button>
                      <button
                        onClick={() => openEdit(t)}
                        className="text-blue-600 hover:text-blue-800"
                      >
                        编辑
                      </button>
                      <button
                        onClick={() => openLogs(t)}
                        className="text-gray-600 hover:text-gray-800"
                      >
                        日志
                      </button>
                      <button
                        onClick={() => handleDelete(t)}
                        className="text-red-600 hover:text-red-800"
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 分页（复用渠道列表交互模式） */}
      {total > 20 && (
        <div className="mt-4 flex items-center justify-between">
          <span className="text-sm text-gray-600">共 {total} 条</span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded border px-3 py-1 text-sm disabled:opacity-50"
            >
              上一页
            </button>
            <span className="px-3 py-1 text-sm">第 {page} 页</span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page * 20 >= total}
              className="rounded border px-3 py-1 text-sm disabled:opacity-50"
            >
              下一页
            </button>
          </div>
        </div>
      )}

      {/* 创建/编辑弹窗 */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="max-h-[90vh] w-full max-w-lg overflow-auto rounded-lg bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-bold">
              {editingTask ? "编辑推送任务" : "新建推送任务"}
            </h2>
            {formError && (
              <div className="mb-3 rounded border border-red-300 bg-red-50 p-2 text-sm text-red-700">
                {formError}
              </div>
            )}
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-sm text-gray-600">任务名称</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full rounded border px-3 py-2 text-sm"
                  placeholder="如：每日热点速报"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm text-gray-600">目标渠道</label>
                <select
                  value={form.bot_channel_id}
                  onChange={(e) => setForm({ ...form, bot_channel_id: e.target.value })}
                  className="w-full rounded border px-3 py-2 text-sm"
                >
                  <option value="">请选择渠道</option>
                  {channels.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm text-gray-600">触发类型</label>
                <div className="flex gap-4">
                  {Object.entries(TRIGGER_LABELS).map(([value, label]) => (
                    <label key={value} className="flex items-center gap-1 text-sm text-gray-700">
                      <input
                        type="radio"
                        name="trigger_type"
                        value={value}
                        checked={form.trigger_type === value}
                        onChange={() => setForm({ ...form, trigger_type: value })}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>

              {/* 4.2 Cron 编辑器：仅 cron 类型显示 */}
              {form.trigger_type === "cron" && (
                <div>
                  <label className="mb-1 block text-sm text-gray-600">定时规则</label>
                  <CronEditor
                    key={`${editingTask?.id ?? "new"}-cron`}
                    value={form.cron_expr}
                    onChange={(expr) => setForm({ ...form, cron_expr: expr })}
                  />
                </div>
              )}

              {/* 事件类型下拉：仅 event 类型显示（表单联动） */}
              {form.trigger_type === "event" && (
                <div>
                  <label className="mb-1 block text-sm text-gray-600">事件类型</label>
                  <select
                    value={form.trigger_event}
                    onChange={(e) => setForm({ ...form, trigger_event: e.target.value })}
                    className="w-full rounded border px-3 py-2 text-sm"
                  >
                    {Object.entries(EVENT_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="mb-1 block text-sm text-gray-600">内容模板</label>
                <textarea
                  value={form.content_template}
                  onChange={(e) => setForm({ ...form, content_template: e.target.value })}
                  rows={4}
                  className="w-full rounded border px-3 py-2 text-sm"
                  placeholder={TEMPLATE_PLACEHOLDER}
                />
                <p className="mt-1 text-xs text-gray-400">
                  支持变量：{"{date} {time} {space_name} {doc_title} {hot_topic} {topic_count}"}
                </p>
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setShowForm(false)}
                className="rounded border px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleSubmit}
                disabled={formLoading}
                className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {formLoading ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 4.3 任务日志弹窗（复用渠道日志样式，按 push_task_id 过滤） */}
      {logsTask && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setLogsTask(null)}
        >
          <div
            className="max-h-[80vh] w-full max-w-2xl overflow-auto rounded-lg bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-4 text-lg font-bold">任务日志：{logsTask.name}</h2>
            {logsLoading ? (
              <div className="py-8 text-center text-gray-500">加载中...</div>
            ) : logs.length === 0 ? (
              <div className="py-8 text-center text-gray-500">暂无该任务的投递日志</div>
            ) : (
              <div className="space-y-2">
                {logs.map((log) => (
                  <div key={log.id} className="rounded border p-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span
                        className={`rounded px-2 py-0.5 text-xs ${
                          log.status === "success"
                            ? "bg-green-100 text-green-700"
                            : "bg-red-100 text-red-700"
                        }`}
                      >
                        {log.status === "success" ? "成功" : "失败"}
                      </span>
                      <span className="text-xs text-gray-400">
                        {log.created_at?.slice(0, 19).replace("T", " ")}
                      </span>
                    </div>
                    <p className="mt-1 text-gray-600">{log.content_preview}</p>
                    {log.error_message && (
                      <p className="mt-1 text-xs text-red-600">{log.error_message}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4 text-right">
              <button
                onClick={() => setLogsTask(null)}
                className="rounded border px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
