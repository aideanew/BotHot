// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * STEP-55 S55.1：mock 路由的**运行时形状门**（P-124 / D-V21-12）。
 *
 * 为什么还要一道门：STEP-52 的三道用例钉住了"路由↔对照表↔后端权威名"，
 * 但**样例到底长成什么样**仍由就地手写的 `satisfies` 保证——把某条的 `satisfies` 摘掉，
 * 覆盖面门、死条目门、对名门、`tsc` 全都不会红（实测读数在 `EVD-V21-52/p124_probe_readings.md`）。
 * 本文件不靠"那句 satisfies 还在不在"：它拿对照表逐条走**真实分发器**
 * （`matchMockRoute` → `buildMockContext` → `route.handle`），再拿**生成好的 schema JSON**
 * 做递归核对。样例多一个键、少一个必填键、枚举取值越界、嵌套对象走形——都在运行时红。
 *
 * 不手写任何键清单（那是造第二个真源，会漂）、不加新依赖（核对器是纯函数，≤80 行）。
 * 遇到本仓 schema 没在用的写法**直接抛错**而不是跳过——和 `gen_contracts.py` 同一个纪律：
 * 一门不知道自己在判什么的安全门，比没有门更坏。
 */

const SCHEMA_FILES = [
  "../../packages/contracts/schemas/shapes.schema.json",
  "../../packages/contracts/schemas/engine.schema.json",
];

type Node = Record<string, unknown>;

/**
 * **只**当注解的关键字：checkShape 既不按它们下钻、也不判它们（`pattern`/`format` 现测各 0 处，
 * 见 EVD-V21-55/s55_1_checker_blindspot_audit.txt）。注意这里**不含**取值范围那一族——
 * 那六个关键字是被判的（见 BOUNDS 与 checkShape 末段），所以它们不许出现在"同级结构键"的豁免名单里，
 * 否则 `$ref` + `minimum` 这种写法会被 auditDefs 当成"只是注解"放过。
 */
const ANNOTATION_ONLY = new Set([
  "$id",
  "$schema",
  "$defs",
  "description",
  "title",
  "default",
  "examples",
  "deprecated",
  "format",
  "pattern",
  "x-generated-by",
  "x-source-module",
]);

/** 取值范围族：本仓契约真声明的约束（现测 minimum 32、maximum 1、minLength 3、maxLength 4） */
const BOUNDS = ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength"];

const ANNOTATIONS = new Set([...ANNOTATION_ONLY, ...BOUNDS]);

const STRUCTURAL = new Set([
  "anyOf",
  "enum",
  "type",
  "properties",
  "required",
  "additionalProperties",
  "items",
]);

function jsonType(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

/** 结构关键字 + 注解关键字 + `$ref` 的并集：核对器拿它做"认不出就抛"，不放任何不认识的写法过去 */
const KNOWN = new Set([...ANNOTATIONS, ...STRUCTURAL, "$ref"]);

/**
 * 只认**自己的**键。用 `in` 会顺原型链：样例里出现一个恰好叫 `toString` 的键，
 * "契约没有此键"那条判据就哑了。属性名撞原型链同样不该赌，故 defs 也走这道（现测：0 个撞名）。
 */
const own = (obj: object, key: string) => Object.prototype.hasOwnProperty.call(obj, key);

function loadDefs(): Record<string, Node> {
  const merged: Record<string, Node> = {};
  for (const rel of SCHEMA_FILES) {
    // 与 s48 同口径：cwd 相对路径（happy-dom 下 import.meta.url 是 http 方案，readFileSync 会拒）
    const doc = JSON.parse(readFileSync(join(process.cwd(), rel), "utf-8")) as {
      $defs?: Record<string, Node>;
    };
    for (const [name, node] of Object.entries(doc.$defs ?? {})) {
      // 用 own 而不是 in：`"constructor" in {}` 是 true，撞名 def 会被误判成"两个文件同名"
      if (own(merged, name)) throw new Error(`两个 schema 文件里有同名 def：${name}（核对器不猜该用哪个）`);
      merged[name] = node;
    }
  }
  return merged;
}

/**
 * 契约写法的体检——把 checkShape 里"今天走不到、但一改 schema 就会静默失效"的判据变成不可能。
 * 为什么必须有这一步：checkShape 只在**被走到**的那一层判"认不出就抛"，样例没填的可选键下面
 * 藏着什么写法它根本没见过；所以这里对整棵 def 树逐位置判。
 * 拒绝的构造（每条都有自己的 toThrow 用例，见下面第二条 it）：
 * ① 对象不写 `additionalProperties` ⇒ "不许出现契约外的键"这条判据哑；
 * ② 数组不写 `items` 或写成 tuple ⇒ 元素层没人看；
 * ③ `$ref` / `anyOf` 与同级结构键并存 ⇒ 那一层的约束被整片无视（checkShape 命中 $ref/anyOf 就 return）；
 * ④ `required` 里的键不在 `properties` ⇒ 在 `additionalProperties:false` 下会把**正确**的样例判红；
 * ⑤ 属性名撞 `Object.prototype` ⇒ own-property 判据也不该冒这个险；
 * ⑥ KNOWN 之外的任何关键字（`oneOf`/`const`/`patternProperties`/`minItems`…）⇒ 装载期就抛，
 *   而不是等某条样例恰好走到那一层才发现门不认识它。
 * 2026-10-26 现测（同一份审计文件）：31 个对象节点全带 additionalProperties（30 false + 1 true=MeWallet）、
 * 10 个数组全带 items、14 个 `$ref` 无同级结构键、anyOf 无同级结构键、required 越界 0、撞原型 0、
 * KNOWN 之外关键字 0。
 */
function auditDefs(defs: Record<string, Node>): void {
  const walk = (node: Node, trail: string) => {
    const unknown = Object.keys(node).find((k) => !KNOWN.has(k));
    if (unknown) throw new Error(`${trail}：契约里出现核对器没实现的写法 "${unknown}"（装载期就抛，不等它被样例走到）`);
    const structural = Object.keys(node).filter((k) => !ANNOTATION_ONLY.has(k));
    if (node["$ref"] !== undefined && structural.length > 1) {
      throw new Error(`${trail}：$ref 与同级结构键（${structural.filter((k) => k !== "$ref").join("/")}）并存，核对器不知道还该不该判这一层`);
    }
    if (node["anyOf"] !== undefined && structural.some((k) => k !== "anyOf")) {
      throw new Error(`${trail}：anyOf 与同级结构键（${structural.filter((k) => k !== "anyOf").join("/")}）并存，先命中分支会整片跳过它们`);
    }
    if (node["type"] === "object") {
      if (!("additionalProperties" in node)) throw new Error(`${trail}：对象没写 additionalProperties，"不许出现契约外的键"这条判据会静默失效`);
      const props = (node["properties"] ?? {}) as Record<string, Node>;
      for (const key of (node["required"] ?? []) as string[]) {
        if (!own(props, key)) throw new Error(`${trail}：required 里的 "${key}" 不在 properties——正确的样例也会被误判红`);
      }
      for (const [key, sub] of Object.entries(props)) {
        if (key in Object.prototype) throw new Error(`${trail}.${key}：属性名撞上 Object.prototype，own-property 判据也不该冒这个险`);
        walk(sub, `${trail}.${key}`);
      }
    }
    if (node["type"] === "array") {
      const items = node["items"];
      if (!items || typeof items !== "object" || Array.isArray(items)) {
        throw new Error(`${trail}：数组的 items 不是单个 schema（实为 ${JSON.stringify(items)}），核对器不猜这种写法`);
      }
      walk(items as Node, `${trail}[]`);
    }
    for (const branch of (node["anyOf"] ?? []) as Node[]) walk(branch, `${trail}()`);
  };
  for (const [name, node] of Object.entries(defs)) walk(node, name);
}

/** 核对 value 是否满足 node；返回错误列表（空=满足）。看不懂的结构直接 throw。 */
function checkShape(
  value: unknown,
  node: Node,
  defs: Record<string, Node>,
  trail: string,
  emptyArrays: string[]
): string[] {
  const bad = Object.keys(node).find((k) => !KNOWN.has(k));
  if (bad) throw new Error(`核对器不认识 ${trail} 上的关键字 "${bad}" —— 请扩展核对器，不要静默放行`);
  const ref = node["$ref"];
  if (ref !== undefined) {
    const name = /^#\/\$defs\/(.+)$/.exec(String(ref))?.[1];
    if (!name || !own(defs, name)) throw new Error(`${trail}：只支持 "#/$defs/<名>" 引用，实得 "${String(ref)}"`);
    return checkShape(value, defs[name], defs, trail, emptyArrays);
  }
  const branches = node["anyOf"] as Node[] | undefined;
  if (branches !== undefined) {
    const failures: string[] = [];
    for (const branch of branches) {
      const scratch: string[] = [];
      const errs = checkShape(value, branch, defs, trail, scratch);
      // 命中任一分支即通过；只把**被选中那条**分支的跳过项记账（没走到的分支里的空数组不算数）
      if (errs.length === 0) { emptyArrays.push(...scratch); return []; }
      failures.push(...errs);
    }
    return [`${trail}：anyOf 的 ${branches.length} 个分支都不满足（${failures[0] ?? "无错误详情"}）`];
  }
  const allowed = node["enum"] as unknown[] | undefined;
  if (allowed !== undefined) {
    return allowed.includes(value) ? [] : [`${trail}：值不在 enum 内（实得类型 ${jsonType(value)}，允许 ${JSON.stringify(allowed)}）`];
  }
  const type = node["type"];
  const errs: string[] = [];
  if (type === "object") {
    if (jsonType(value) !== "object") return [`${trail}：契约要求对象，实为 ${jsonType(value)}`];
    const props = (node["properties"] ?? {}) as Record<string, Node>;
    const obj = value as Record<string, unknown>;
    for (const key of (node["required"] ?? []) as string[]) {
      if (!own(obj, key)) errs.push(`${trail}.${key}：契约必填，样例里没有这个键`);
    }
    // 没写 additionalProperties 的对象在门口就被 auditDefs 拦下，所以这里不必猜"没写＝放行还是禁"
    if (node["additionalProperties"] === false) {
      for (const key of Object.keys(obj)) {
        if (!own(props, key)) errs.push(`${trail}.${key}：契约 properties 里没有此键（additionalProperties:false）`);
      }
    }
    for (const [key, sub] of Object.entries(props)) {
      if (own(obj, key)) errs.push(...checkShape(obj[key], sub, defs, `${trail}.${key}`, emptyArrays));
    }
    return errs;
  }
  if (type === "array") {
    if (jsonType(value) !== "array") return [`${trail}：契约要求数组，实为 ${jsonType(value)}`];
    // 空数组没有元素可核对——记一笔，防"样例退化成空"悄悄关掉元素层（清单由上面那条用例逐条写理由）
    if ((value as unknown[]).length === 0) { emptyArrays.push(trail); return []; }
    const items = node["items"] as Node;
    (value as unknown[]).forEach((el, i) => errs.push(...checkShape(el, items, defs, `${trail}[${i}]`, emptyArrays)));
    return errs;
  }
  if (typeof type !== "string") throw new Error(`${trail}：这一层没有可核对的 type（${JSON.stringify(node)}）`);
  const actual = jsonType(value);
  if (actual !== type && !(type === "integer" && actual === "number")) return [`${trail}：契约要求 ${type}，实为 ${actual}`];
  // 取值范围也判：schema 里现测有 32 处 minimum、1 处 maximum、3 处 minLength、4 处 maxLength，
  // 而 limit≥1、qualityScore 0..100、count≥0 正是样例最容易漂的位——只判类型等于漏掉一半。
  const bump = (kw: string, ok: boolean) => {
    if (kw in node && !ok) errs.push(`${trail}：不满足契约的 ${kw}=${String(node[kw])}（实为 ${JSON.stringify(value)}）`);
  };
  const num = value as number;
  const len = typeof value === "string" ? value.length : 0;
  if (type === "integer" && !Number.isInteger(num)) errs.push(`${trail}：契约要求整数，实为 ${num}（非整数）`);
  bump("minimum", num >= (node["minimum"] as number));
  bump("maximum", num <= (node["maximum"] as number));
  bump("exclusiveMinimum", num > (node["exclusiveMinimum"] as number));
  bump("exclusiveMaximum", num < (node["exclusiveMaximum"] as number));
  bump("minLength", len >= (node["minLength"] as number));
  bump("maxLength", len <= (node["maxLength"] as number));
  return errs;
}

/** 路径参数默认填 `x1`；读类样例要命中真数据的用真 id，改写类的故意指向不存在的 id ⇒ 源样本不被污染 */
const ROUTE_OVERRIDES: Record<string, { path?: string; body?: unknown; login?: boolean }> = {
  "GET /api/v1/auth/me": { login: true },
  "POST /api/v1/auth/logout": { login: true },
  "PATCH /api/v1/spaces/{id}/engine": { path: "/api/v1/spaces/sp-001/engine", body: { engine: "builtin" } },
  "POST /api/v1/spaces/{id}/links": { path: "/api/v1/spaces/sp-001/links", body: {} },
  "POST /api/v1/resolve": { body: { url: "https://mp.weixin.qq.com/s/mock-probe" } },
  "POST /api/v1/extract": { body: { url: "https://mp.weixin.qq.com/s/mock-probe" } },
  "POST /api/v1/spaces/{id}/docs": { path: "/api/v1/spaces/sp-001/docs" },
  "GET /api/v1/spaces/{id}/docs/{docId}/status": { path: "/api/v1/spaces/sp-001/docs/doc-nope/status" },
  "POST /api/v1/spaces": { body: { name: "探针空间", description: "" } },
  "GET /api/v1/spaces/{id}/docs": { path: "/api/v1/spaces/sp-001/docs" },
  "GET /api/v1/spaces/{id}/docs:categories": { path: "/api/v1/spaces/sp-001/docs:categories" },
  "DELETE /api/v1/spaces/{id}/docs/{docId}": { path: "/api/v1/spaces/sp-001/docs/doc-nope" },
  "PATCH /api/v1/spaces/{id}/docs/{docId}": {
    path: "/api/v1/spaces/sp-001/docs/doc-nope",
    body: { category: "AI·技术" },
  },
  "POST /api/v1/spaces/{id}/docs:delete": { path: "/api/v1/spaces/sp-001/docs:delete", body: { ids: ["doc-nope"] } },
  "POST /api/v1/spaces/{id}/docs:recategorize": {
    path: "/api/v1/spaces/sp-001/docs:recategorize",
    body: { ids: ["doc-nope"], category: "其他" },
  },
  "GET /api/v1/spaces/{id}": { path: "/api/v1/spaces/sp-001" },
  "DELETE /api/v1/spaces/{id}": { path: "/api/v1/spaces/sp-nope" },
  "PUT /api/v1/system/notifications/read": { body: {} },
};

async function dispatcher() {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_MOCK", "true");
  const routes = await import("@/lib/api/mock-routes");
  const map = await import("@/lib/api/mock-contract-map");
  return { routes, map };
}

function samplePath(key: string, override?: { path?: string }): string {
  if (override) return override.path ?? key.slice(key.indexOf(" ") + 1);
  return key.slice(key.indexOf(" ") + 1).replace(/\{[^}]+\}/g, "x1");
}

describe("S55 mock 响应的运行时形状（直读 schema，不靠 satisfies 是否还在）", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("mock 态不该发 fetch")))
    );
  });

  const emptyArrays: string[] = [];

  it("22 条逐条走真实分发器并按 schema 核对（含条数与跳过项）", async () => {
    const { routes, map } = await dispatcher();
    const defs = loadDefs();
    auditDefs(defs);
    // 样例输入表（ROUTE_OVERRIDES）的键必须是表里的路由：路由改名后旧键不会报错，只会让那条
    // 路由退回默认路径参数 `x1` ⇒ 写类样例变成"未命中"分支，元素层照旧核对却根本没走成功路径。
    const staleOverrides = Object.keys(ROUTE_OVERRIDES).filter((k) => !own(map.MOCK_CONTRACT_MAP, k));
    expect(staleOverrides, `ROUTE_OVERRIDES 里有对照表没有的键：${staleOverrides.join("、")}`).toEqual([]);
    const errors: string[] = [];
    let dispatched = 0;

    /** 走一次真实分发并核对；label 参与报错前缀，同一契约的不同分支用不同 label 区分。 */
    const probe = (label: string, key: string, contractName: string, body?: unknown, search = "") => {
      const method = key.slice(0, key.indexOf(" "));
      const override = ROUTE_OVERRIDES[key];
      const path = samplePath(key, override);
      if (override?.login) routes.mockMarkLoggedIn();
      const matched = routes.matchMockRoute(method, path);
      if (!matched) {
        errors.push(`${label}：真实分发器没匹配到路由（path=${path}）——对照表与注册面脱节`);
        return;
      }
      // "匹配到一条路由"不等于"匹配到表里这条"：两条表项共用一个契约名（SpaceDetail），
      // 若某条 pattern 写得能吃邻路由的样例路径，这里不钉住就会拿 A 的响应去比 B 的契约。
      const want = key.replace(/\{[^}]+\}/g, "{seg}");
      const got = map.normalizeRouteKey(matched.route.method, matched.route.pattern.source);
      if (got !== want) errors.push(`${label}：分发器匹配到的是另一条路由（表里 "${want}"，实际 "${got}"）`);
      // paramNames 声明了几个 ≠ pattern 真捕了几段。旧写法只在 `paramNames?.length` 非零时比数量，
      // 于是"把某条的 paramNames 删掉"这一刀整条跳过：matchMockRoute 解出空 params、handler 读到
      // `params.docId ?? ""` 走兜底分支，响应照样合契约，而本该走的那条分支根本没跑。
      // 这里改成直接数 pattern 里的捕获组（`\(` 后面不是 `?` 才算捕获组）。
      const groups = (matched.route.pattern.source.match(/\((?!\?)/g) ?? []).length;
      const names = matched.route.paramNames?.length ?? 0;
      if (names !== groups) errors.push(`${label}：pattern 捕 ${groups} 段，paramNames 只声明 ${names} 个`);
      const ctxParams = Object.keys(matched.params).length;
      if (ctxParams !== groups) errors.push(`${label}：pattern 捕 ${groups} 段，实解出 ${ctxParams} 个`);
      const rawBody = body === undefined ? (override?.body === undefined ? null : JSON.stringify(override.body)) : JSON.stringify(body);
      const ctx = routes.buildMockContext(method, path, search, matched.params, rawBody);
      let response: unknown;
      try {
        response = matched.route.handle(ctx);
      } catch (exc) {
        errors.push(`${label}：handler 抛错（${exc instanceof Error ? exc.message : String(exc)}）`);
        return;
      }
      // 分页壳的 limit/offset 是**回显请求值**的（STEP-52 对账过后端 `limit_offset_query` 的口径），
      // 而默认那 22 发一律传空 search ⇒ 只判过缺省形。带 query 这一发把"回显"那条腿也走一遍：
      // handler 若把请求里的页宽吃掉换成写死值，这里就红，而不是等 tsc 判一个合法数字。
      if (search) {
        const q = new URLSearchParams(search);
        const obj = response as Record<string, unknown>;
        for (const k of ["limit", "offset"]) {
          if (own(obj, k) && obj[k] !== Number(q.get(k))) {
            errors.push(`${label}：分页 ${k} 没回显请求值（query 里是 ${String(q.get(k))}，响应给的是 ${String(obj[k])}）`);
          }
        }
      }
      dispatched += 1;
      const def = own(defs, contractName) ? defs[contractName] : undefined;
      if (!def) {
        errors.push(`${label}：schema 里没有 def "${contractName}"`);
        return;
      }
      errors.push(...checkShape(response, def, defs, `${contractName}←${label}`, emptyArrays));
    };

    for (const [key, contractName] of Object.entries(map.MOCK_CONTRACT_MAP)) {
      probe(key, key, contractName);
    }
    // 同一契约的另一条成功分支：抽取的低质样例（`qualityReasons` 非空那一支）。
    // 只跑默认分支的话，"某个分支的样例走形"就没人看——这条是补那一半，不是凑数。
    probe("POST /api/v1/extract（低质分支）", "POST /api/v1/extract", "ExtractedArticleView", {
      url: "https://mp.weixin.qq.com/s/低质样例",
    });
    // 分页回显那一发（见 probe 内注释）：同一张路由，换了 query 就必须换出响应里的 limit/offset。
    probe("GET /api/v1/spaces（带 query 的分页回显）", "GET /api/v1/spaces", "SpacePage", undefined, "limit=7&offset=3");

    expect(dispatched, "被真实分发并核对的次数（22 条 + 低质抽取那一支 + 带 query 的分页那一支）").toBe(24);
    // 全表里"数组是空的、因而元素层无从核对"的位置共三处（现测得，不是推测），每条都有实据：
    // · 通知历史：演示态没有真实历史 ⇒ 空页（见 mock-routes 该条注释）；
    // · 抽取-高质量：qualityReasons 为空（高质量没有理由可列）；
    // · 抽取-低质：images 为空（营销号短文无配图）。
    // 关键是**两分支合起来把 `ExtractedArticleView` 的两个数组都真核对过**：images 在非空的那支
    // （高质量）里逐元素核对，qualityReasons 在非空的那支（低质）里核对。
    // 新增第四条必须写清为什么，否则就是"某个样例悄悄退化成空数组、元素形状没人看了"。
    expect(
      emptyArrays,
      `元素层被跳过的空数组位置（要新增必须写进注释说明为什么）：${emptyArrays.join("、")}`
    ).toEqual([
      "ExtractedArticleView←POST /api/v1/extract.qualityReasons",
      "NotificationHistoryPage←GET /api/v1/system/notifications/history.items",
      "ExtractedArticleView←POST /api/v1/extract（低质分支）.images",
    ]);
    expect(errors, `与契约不同形：\n  ${errors.join("\n  ")}`).toEqual([]);
  });

  it("核对器自检：手造坏样本各自必须报错，合法样本必须通过，体检门的七条拒绝路径各自要证明会红", () => {
    const defs = loadDefs();
    auditDefs(defs);
    const wallet = { balanceYuan: "0.00", currency: "CNY" };

    const missing = checkShape(
      { items: [], total: 0, limit: 50, offset: 0 },
      defs["NotificationHistoryPage"],
      defs,
      "坏1缺键",
      []
    );
    expect(missing.length, `缺必填键必须报：${JSON.stringify(missing)}`).toBeGreaterThan(0);

    const extra = checkShape(
      { ok: true, docId: "d", docs: 1, assets: 0, "莫属键": 1 },
      defs["DocDeleteResult"],
      defs,
      "坏2多键",
      []
    );
    expect(extra.length, `多一个契约外的键必须报：${JSON.stringify(extra)}`).toBeGreaterThan(0);

    const badEnum = checkShape(
      { docId: "d", langbotFileId: "f", status: "DONE" },
      defs["DocIngestState"],
      defs,
      "坏3枚举外",
      []
    );
    expect(badEnum.length, `枚举外取值必须报：${JSON.stringify(badEnum)}`).toBeGreaterThan(0);

    expect(
      checkShape(
        { id: "s", name: "n", description: "", docCount: 0, updatedAt: "t", engine: "builtin", engineKbId: "kb", isPublic: false },
        defs["SpaceView"],
        defs,
        "合法",
        []
      ),
      "合法样本不该报"
    ).toEqual([]);
    // MeWallet 是契约里唯一的开放对象（additionalProperties:true，P-121）⇒ 多键放过是**契约说的**，不是门松了
    expect(checkShape({ ...wallet, "未知扩展": "x" }, defs["MeWallet"], defs, "开放对象", [])).toEqual([]);
    expect(() => checkShape({}, { allOf: [] } as unknown as Node, defs, "不认识的写法", [])).toThrow(
      /核对器不认识/
    );
    // 取值范围（schema 里 32 处 minimum / 1 处 maximum / 3 处 minLength / 4 处 maxLength）也要真判：
    // NotificationHistoryPage.limit 契约写 minimum:1，给 0 必须红——光判"是整数"会让页宽 0 这种漂移交付过去。
    expect(
      checkShape({ items: [], total: 0, limit: 0, offset: 0 }, defs["NotificationHistoryPage"], defs, "越界", []),
      "低于契约 minimum 的整数必须报"
    ).toEqual(expect.arrayContaining([expect.stringContaining("minimum")]));
    // 体检门的四条拒绝路径逐条证明它会红（不证就等于写了一道从没跑过的门）
    expect(() => auditDefs({ X: { type: "object", properties: {} } })).toThrow(/additionalProperties/);
    expect(() => auditDefs({ X: { type: "array" } })).toThrow(/items/);
    expect(() => auditDefs({ X: { $ref: "#/$defs/Y", type: "object" } })).toThrow(/\$ref 与同级结构键/);
    expect(() => auditDefs({ X: { type: "object", additionalProperties: false, properties: { constructor: { type: "string" } } } })
    ).toThrow(/Object\.prototype/);
    expect(() => auditDefs({ X: { anyOf: [{ type: "string" }], type: "object" } })).toThrow(/anyOf 与同级结构键/);
    expect(() =>
      auditDefs({ X: { type: "object", additionalProperties: false, properties: {}, required: ["没有这个属性"] } })
    ).toThrow(/required 里的/);
    expect(() => auditDefs({ X: { oneOf: [{ type: "string" }] } } as unknown as Record<string, Node>)).toThrow(
      /核对器没实现的写法/
    );
  });
});
