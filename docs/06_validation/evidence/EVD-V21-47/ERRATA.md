# ERRATA — EVD-V21-47

本目录的已归档原文按纪律**不回改**（STEP-56 S56.4，D-V21-16）。这里只登记读数的适用范围。

- `s47_red_extra_key.txt:2` 记的是 `tests/test_shapes_response_contract.py:43: AssertionError`。
  现核对交付字节：`_check` 的 `assert` 在 **:50**，**:43 是空行**。
  这个行号**从未对应过任何已提交版本**，三条读数一起构成论证：
  ① `git log --all --format=%h -- apps/api/tests/test_shapes_response_contract.py` = **1 个提交**
  （`f4f0261`，STEP-47 交付批本身）；② `git log --format=%h f4f0261..HEAD -- 同一路径` = **空**；
  ③ `git show f4f0261:apps/api/tests/test_shapes_response_contract.py` 的第 43 行是空行、
  第 50 行才是那条 `assert`。
  ⇒ 该文件从头到尾只有一个已提交版本，而那个版本里 `:43` 就不是断言行；`s47` 那次运行是
  **开发中途的工作态**，不是交付字节。
- 那条红本身仍然成立，也不因本条而失去效力：诊断文本与键路径（`SpacePage` 的 `probeExtra`
  被 `additionalProperties: false` 拒掉、`['items', 0]`）就是当时真实输出。今天判着相邻两类事的
  常驻用例要说清各自的范围：`test_closed_objects_reject_extra_and_missing_keys` 判"封闭对象多一个键
  就红"这条判据本身（它用的 def 是 `SpaceDeleteResult`，不是 `SpacePage`）；`SpacePage` 这个契约名
  与它 `items` 元素的形状由本文件里的真端点反向核判着（`test_spaces_crud_shapes` 判线上响应并带
  `items` 非空的断言）；前端 `s55-mock-runtime-shape.spec.ts` 判的是**演示态样例**与契约同形，
  不是后端序列化——那是另一条腿，不要混着引。要复算"多一个契约外键会红"，
  跑 `pytest tests/test_shapes_response_contract.py` 即可，不必依赖这份归档输出的行号。
- **引用这条红时的行号写 `:50`**，不要写 `:43`。
