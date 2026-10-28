import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

/**
 * STEP-59 59.2 —— 真后端 e2e 的三角色 storageState 生成（Playwright globalSetup）。
 *
 * 会话**不在这里造**：`scripts/e2e/run_real_backend.sh` 调 `apps/api/scripts/qa_seed_sessions.py`
 * 往 Redis 写三条会话，并把它的 stdout 落成 seed 文件；本文件只解析那份读数，
 * 因此 e2e 用的身份与 `qa_seed_sessions.py:37-39` 的 `ACCOUNTS` 不可能漂移。
 *
 * cookie 名取自 seed 行里的 `cookie=` 字段，不在此手抄 `bothot_session`——那个值属于
 * `apps/api/app/core/config.py:50`，抄一份过来就等于把改它的权利留在了前端。
 *
 * 注入的 cookie 五项属性按后端 `_set_session_cookie`（`app/api/v1/auth.py:93-100`）对齐：
 * name、path=/、httpOnly=true、sameSite=Lax、secure=false（`session_cookie_secure`
 * 默认 false，config.py:52；这里是浏览器侧注入，写 true 会让 chromium 在 http://localhost
 * 上直接丢掉它）。唯一不镜像的是 `max_age`（config.py:51 的 7 天）——这里用会话级
 * `expires: -1`：一次 run 之内不需要跨重启存活，而 Playwright 的负数到期时间只接受 -1。
 * httpOnly 保持 true 与后端一致，顺带让用例无法靠改本地状态冒充登录态。
 *
 * 为什么会话非得放 Redis：`SESSION_STORE_BACKEND` 默认 `memory`（config.py:55），
 * memory 是**进程内**存储，种子脚本与 uvicorn 是两个进程 ⇒ "脚本说写成功了、后端说没这条会话"
 * 这种静默失效。启动器因此显式导出 redis。
 */

/** seed 里的 sub → 要产出的 storageState 文件名（三角色一张表，新增角色只加一行） */
const SEED_SUB_TO_ROLE: Record<string, string> = {
  "qa-admin-001": "admin",
  "qa-operator-001": "operator",
  "qa-user-001": "user",
};

/** 行形状由 `qa_seed_sessions.py:74` 的 print 决定：`session <sub>: cookie=<name> value=<id>` */
const SEED_LINE = /^session (\S+): cookie=(\S+) value=(\S+)$/;

/** 与启动器 `RUN_DIR="${E2E_RUN_DIR:-${RUNNER_TEMP:-/tmp}/e2e-real}"` 同一条式子：
 *  只认 E2E_SEED_FILE 不认 E2E_RUN_DIR 的话，设了 E2E_RUN_DIR 的那一棒两边会算出不同路径，
 *  于是 seed 明明写了、这里读不到——又是一个静默失效位。 */
function defaultSeedFile(): string {
  const runDir = process.env.E2E_RUN_DIR ?? path.join(process.env.RUNNER_TEMP ?? "/tmp", "e2e-real");
  return path.join(runDir, "seed.txt");
}

export default async function realBackendStorageStateSetup(): Promise<void> {
  const seedFile = process.env.E2E_SEED_FILE ?? defaultSeedFile();
  if (!existsSync(seedFile)) {
    throw new Error(
      `real.setup 读不到 seed 文件：${seedFile}\n` +
        `  先跑 bash scripts/e2e/run_real_backend.sh（它把 seed 写到 \${RUNNER_TEMP:-/tmp}/e2e-real/seed.txt，` +
        `  并在日志里打印该路径；CI 步骤显式设 E2E_SEED_FILE，本机也可显式指定同一个值）`,
    );
  }
  const authDir = process.env.E2E_AUTH_DIR ?? path.join(process.cwd(), "e2e", ".auth");
  mkdirSync(authDir, { recursive: true });

  const found = new Map<string, { name: string; value: string }>();
  const malformed: string[] = [];
  for (const raw of readFileSync(seedFile, "utf8").split(/\r?\n/)) {
    if (!raw.startsWith("session ")) continue;
    const m = SEED_LINE.exec(raw.trim());
    if (m === null) {
      // 只带形状不带值：值就是会话凭据，不进日志（也不进 CI 归档）
      malformed.push(raw.slice(0, 24));
      continue;
    }
    const sub = m[1] as string;
    const role = SEED_SUB_TO_ROLE[sub];
    if (role !== undefined) {
      found.set(role, { name: m[2] as string, value: m[3] as string });
    }
  }

  if (malformed.length > 0) {
    throw new Error(
      `seed 里有 ${malformed.length} 行以 "session " 开头却不匹配 \`session <sub>: cookie=<n> value=<v>\`：` +
        `${malformed.join(" | ")}\n  说明 qa_seed_sessions.py 的输出格式变了 ⇒ 这里必须跟着改，不能放宽正则`,
    );
  }
  const missing = Object.values(SEED_SUB_TO_ROLE).filter((role) => !found.has(role));
  if (missing.length > 0) {
    throw new Error(
      `seed 里缺角色会话：${missing.join(", ")}（已取到 ${[...found.keys()].join(", ") || "无"}）` +
        ` ⇒ seed 文件可能来自旧版本脚本或被截断：${seedFile}`,
    );
  }

  // 三角色共用同一个 cookie 名（后端只认一个键），取 admin 行那份即可
  const cookieName = (found.get("admin") as { name: string }).name;
  const written: string[] = [];
  for (const role of ["admin", "operator", "user"]) {
    const cookie = found.get(role) as { name: string; value: string };
    if (cookie.name !== cookieName) {
      throw new Error(`seed 里 ${role} 的 cookie 名与 admin 不一致：${cookie.name}`);
    }
    const state = {
      cookies: [
        {
          name: cookie.name,
          value: cookie.value,
          domain: "localhost",
          path: "/",
          expires: -1, // 会话级 cookie：随 context 结束即失效。选 -1 而不是换算一个未来时刻，
                       // 是因为 Playwright 的负数到期时间只接受 -1（`expires === -1 ? void 0 : …`），
                       // 而这一档的会话本来就不需要跨 run 存活（种子脚本给后端的那份才有 7 天 TTL）。
          httpOnly: true,
          secure: false,
          sameSite: "Lax",
        },
      ],
      origins: [],
    };
    const file = path.join(authDir, `${role}.json`);
    writeFileSync(file, `${JSON.stringify(state, null, 2)}\n`, "utf8");
    written.push(path.relative(process.cwd(), file));
  }

  console.log(
    `real.setup：由 ${seedFile} 生成 ${written.join(", ")}（cookie=${cookieName}，值不打印）`,
  );
}
