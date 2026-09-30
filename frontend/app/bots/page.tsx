"use client";

/**
 * 机器人渠道管理页。
 *
 * 功能：
 * - 渠道列表（分页、类型筛选、状态筛选）
 * - 创建渠道（弹窗表单）
 * - 编辑渠道
 * - 测试推送
 * - 查看推送日志
 * - 删除渠道
 * - 推送任务管理（定时推送）
 */

import { useCallback, useEffect, useState } from "react";
import {
  createChannel,
  deleteChannel,
  listChannelTypes,
  listChannels,
  listPushLogs,
  testPush,
  updateChannel,
  type BotChannel,
  type ChannelType,
  type PushLog,
} from "@/lib/api/bots";
import { usePageTitle } from "@/components/usePageTitle";
import { useAuth } from "@/components/AuthContext";
import PushTasksTab from "@/components/PushTasksTab";

const CHANNEL_LABELS: Record<string, string> = {
  feishu: "飞书",
  dingtalk: "钉钉",
  wechat_work: "企业微信",
  webhook: "通用 Webhook",
  wechat_clawbot: "微信 ClawBot",
  web: "站内通知",
};

const STATUS_LABELS: Record<string, string> = {
  active: "启用",
  disabled: "已禁用",
  deleted: "已删除",
};

export default function BotsPage() {
  // W4 4.1：页面拆为「推送渠道 / 推送任务」两个 Tab
  const [activeTab, setActiveTab] = useState<"channels" | "tasks">("channels");
  const { me } = useAuth();
  const [channels, setChannels] = useState<BotChannel[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [channelTypes, setChannelTypes] = useState<ChannelType[]>([]);

  // 创建/编辑弹窗
  const [showForm, setShowForm] = useState(false);
  const [editingChannel, setEditingChannel] = useState<BotChannel | null>(null);
  const [formData, setFormData] = useState({
    name: "",
    channel_type: "feishu",
    webhook_url: "",
    secret: "",
    extra_config: "{}",
  });
  const [formError, setFormError] = useState("");
  const [formLoading, setFormLoading] = useState(false);

  // 日志弹窗
  const [showLogs, setShowLogs] = useState(false);
  const [logs, setLogs] = useState<PushLog[]>([]);
  const [logsChannelId, setLogsChannelId] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);

  // 测试推送状态
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string>("");

  const fetchChannels = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await listChannels({ page, page_size: 20 });
      setChannels(res.items || []);
      setTotal(res.total || 0);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载渠道列表失败");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchChannels();
  }, [fetchChannels]);

  useEffect(() => {
    listChannelTypes().then(setChannelTypes).catch(() => {});
  }, []);

  usePageTitle("机器人渠道管理");

  const handleCreate = () => {
    setEditingChannel(null);
    setFormData({
      name: "",
      channel_type: "feishu",
      webhook_url: "",
      secret: "",
      extra_config: "{}",
    });
    setFormError("");
    setShowForm(true);
  };

  const handleEdit = (ch: BotChannel) => {
    setEditingChannel(ch);
    setFormData({
      name: ch.name,
      channel_type: ch.channel_type,
      webhook_url: ch.webhook_url,
      secret: "",
      extra_config: ch.extra_config,
    });
    setFormError("");
    setShowForm(true);
  };

  const handleSubmit = async () => {
    setFormError("");
    setFormLoading(true);
    try {
      if (editingChannel) {
        await updateChannel(editingChannel.id, {
          name: formData.name,
          webhook_url: formData.webhook_url,
          secret: formData.secret,
          extra_config: formData.extra_config,
        });
      } else {
        await createChannel({
          name: formData.name,
          channel_type: formData.channel_type,
          webhook_url: formData.webhook_url,
          secret: formData.secret,
          extra_config: formData.extra_config,
        });
      }
      setShowForm(false);
      fetchChannels();
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此渠道？此操作不可撤销。")) return;
    try {
      await deleteChannel(id);
      fetchChannels();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const handleTest = async (id: string) => {
    setTestingId(id);
    setTestResult("");
    try {
      const res = await testPush(id);
      setTestResult(
        res.delivered
          ? `✅ 推送成功（渠道: ${res.channel}）`
          : `❌ 推送失败: ${res.reason}`,
      );
    } catch (e: unknown) {
      setTestResult(`❌ 测试失败: ${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setTestingId(null);
    }
  };

  const handleViewLogs = async (channelId: string) => {
    setLogsChannelId(channelId);
    setShowLogs(true);
    setLogsLoading(true);
    try {
      const res = await listPushLogs(channelId, { page: 1, page_size: 50 });
      setLogs(res.items || []);
    } catch {
      setLogs([]);
    } finally {
      setLogsLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">机器人渠道管理</h1>
        {activeTab === "channels" && (
          <button
            onClick={handleCreate}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            + 新建渠道
          </button>
        )}
      </div>

      {/* Tab 切换（胶囊样式与 /hot 页类型筛选一致） */}
      <div className="mb-6 flex gap-2" role="tablist" aria-label="机器人管理子页">
        <button
          role="tab"
          aria-selected={activeTab === "channels"}
          onClick={() => setActiveTab("channels")}
          className={`rounded px-3 py-1.5 text-sm ${
            activeTab === "channels"
              ? "bg-blue-600 text-white"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          推送渠道
        </button>
        <button
          role="tab"
          aria-selected={activeTab === "tasks"}
          onClick={() => setActiveTab("tasks")}
          className={`rounded px-3 py-1.5 text-sm ${
            activeTab === "tasks"
              ? "bg-blue-600 text-white"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          推送任务
        </button>
      </div>

      {activeTab === "tasks" ? (
        <PushTasksTab userSub={me?.sub ?? ""} />
      ) : (
        <>
      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {testResult && (
        <div className="mb-4 rounded border border-blue-300 bg-blue-50 p-3 text-sm text-blue-700">
          {testResult}
        </div>
      )}

      {/* 渠道类型说明 */}
      {channelTypes.length > 0 && (
        <div className="mb-6 rounded border border-gray-200 bg-gray-50 p-4">
          <h2 className="mb-2 text-sm font-semibold text-gray-700">可用渠道类型</h2>
          <div className="flex flex-wrap gap-2">
            {channelTypes.map((ct) => (
              <span
                key={ct.channel}
                className="rounded bg-white px-2 py-1 text-xs text-gray-600 ring-1 ring-gray-200"
                title={ct.description}
              >
                {CHANNEL_LABELS[ct.channel] || ct.channel}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 渠道列表 */}
      {loading ? (
        <div className="py-12 text-center text-gray-500">加载中...</div>
      ) : channels.length === 0 ? (
        <div className="py-12 text-center text-gray-500">
          暂无渠道，点击「新建渠道」创建第一个机器人推送渠道。
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg ring-1 ring-gray-200">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">名称</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">渠道</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">状态</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">推送统计</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {channels.map((ch) => (
                <tr key={ch.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">{ch.name}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {CHANNEL_LABELS[ch.channel_type] || ch.channel_type}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded px-2 py-0.5 text-xs ${
                        ch.status === "active"
                          ? "bg-green-100 text-green-700"
                          : ch.status === "disabled"
                            ? "bg-gray-100 text-gray-600"
                            : "bg-red-100 text-red-700"
                      }`}
                    >
                      {STATUS_LABELS[ch.status] || ch.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {ch.success_push_count} / {ch.total_push_count} 成功
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleTest(ch.id)}
                        disabled={testingId === ch.id}
                        className="text-blue-600 hover:text-blue-800 disabled:opacity-50"
                      >
                        {testingId === ch.id ? "测试中..." : "测试"}
                      </button>
                      <button
                        onClick={() => handleViewLogs(ch.id)}
                        className="text-gray-600 hover:text-gray-800"
                      >
                        日志
                      </button>
                      <button
                        onClick={() => handleEdit(ch)}
                        className="text-blue-600 hover:text-blue-800"
                      >
                        编辑
                      </button>
                      <button
                        onClick={() => handleDelete(ch.id)}
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

      {/* 分页 */}
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
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-bold">
              {editingChannel ? "编辑渠道" : "新建渠道"}
            </h2>
            {formError && (
              <div className="mb-3 rounded border border-red-300 bg-red-50 p-2 text-sm text-red-700">
                {formError}
              </div>
            )}
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-sm text-gray-600">渠道名称</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full rounded border px-3 py-2 text-sm"
                  placeholder="如：飞书技术群"
                />
              </div>
              {!editingChannel && (
                <div>
                  <label className="mb-1 block text-sm text-gray-600">渠道类型</label>
                  <select
                    value={formData.channel_type}
                    onChange={(e) => setFormData({ ...formData, channel_type: e.target.value })}
                    className="w-full rounded border px-3 py-2 text-sm"
                  >
                    {channelTypes.map((ct) => (
                      <option key={ct.channel} value={ct.channel}>
                        {CHANNEL_LABELS[ct.channel] || ct.channel}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <div>
                <label className="mb-1 block text-sm text-gray-600">
                  Webhook URL{editingChannel ? "（留空不改）" : ""}
                </label>
                <input
                  type="text"
                  value={formData.webhook_url}
                  onChange={(e) => setFormData({ ...formData, webhook_url: e.target.value })}
                  className="w-full rounded border px-3 py-2 text-sm"
                  placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm text-gray-600">
                  签名密钥{editingChannel ? "（留空不改）" : "（可选，加签模式时填写）"}
                </label>
                <input
                  type="password"
                  value={formData.secret}
                  onChange={(e) => setFormData({ ...formData, secret: e.target.value })}
                  className="w-full rounded border px-3 py-2 text-sm"
                  placeholder="加签密钥"
                />
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

      {/* 日志弹窗 */}
      {showLogs && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setShowLogs(false)}
        >
          <div
            className="max-h-[80vh] w-full max-w-2xl overflow-auto rounded-lg bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-4 text-lg font-bold">推送日志</h2>
            {logsLoading ? (
              <div className="py-8 text-center text-gray-500">加载中...</div>
            ) : logs.length === 0 ? (
              <div className="py-8 text-center text-gray-500">暂无推送日志</div>
            ) : (
              <div className="space-y-2">
                {logs.map((log) => (
                  <div
                    key={log.id}
                    className="rounded border p-3 text-sm"
                  >
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
                onClick={() => setShowLogs(false)}
                className="rounded border px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
        </>
      )}
    </div>
  );
}
