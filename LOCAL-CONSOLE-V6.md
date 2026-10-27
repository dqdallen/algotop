# AlgoTop v6 本地采集台（未部署）

这是独立于现有公开静态站的本地管理工具。不写 GitHub，不发布、不启用定时任务，不修改题库、答案或频次。

## 启动

```sh
cd /path/to/algotop-v6
python tools/local_console.py --port 8765
```

在同一台电脑访问 **http://127.0.0.1:8765**。只绑定 `127.0.0.1`；不支持远程暴露、反向代理、隧道或 `0.0.0.0`。停止用 Ctrl+C。页面要求精确的 Host/Origin，包括端口；不要换成 localhost。

以下为历史 v6 说明；当前版本的启动与验收以根目录 `README.md` 和 `USER-ACCEPTANCE.md` 为准。可选正文解析器和 OpenAI SDK 需在自己的环境按需安装：

```sh
python -m venv .venv
.venv/bin/pip install -r tools/collection/requirements-parser.txt -r tools/collection/requirements-llm.txt
.venv/bin/python tools/local_console.py
```

没有可选依赖也可运行人工模拟演示；HTML 使用受限的内置可见文字解析作为回退。界面显示实际解析器、版本和回退原因。解析器不能解锁登录、验证码、robots 或来源授权限制。

## 操作

1. 输入来源 HTTPS 链接，点击“检查策略并获取”。复用既有日期/路径/正文授权/robots/出口控制，不扩大现有许可。策略受阻时显示明确错误代码，并打开手工导入入口。
2. 使用自己合法获得的正文或 UTF-8 HTML 文件。链接仅作用户声明的来源，不作为真实性或使用权证明。HTML 不执行脚本、不加载外部资源。
3. 审核规范化正文、来源与哈希；偏移以该正文的 Python Unicode 字符索引为准。
4. 可先“载入演示 / 人工测试模拟”：固定虚构材料及预设提取结果，经相同证据验证与候选流程。它不使用在线模型，也不证明真实模型提取效果。
5. 真实模型提取必须先在服务端配置，再逐次勾选正文审核与发送同意。控制台不接收密钥。演示材料不会被发送给收费 API。
6. 取消勾选个人项目细节或不合格候选，导出服务器生成的 JSON。不能通过网页改写证据、来源或注入候选。导出保留 `pending_human_approval`、`countEligible=false`、零新增频次和 `published=false`。短证据片段也可能敏感，保存到私有位置。

新导入/新链接/清空会立即使旧候选失效；失败导入也不会继续导出旧结果。多个标签页共用一次本地会话，旧标签页的文档 ID 会被拒绝。内存会话不落盘；刷新页面不会恢复浏览器视图，点击清空或停止进程可释放服务端状态。下载文件不会被“清空”删除。

## 未来配置真实 OpenAI

只在服务端环境或用户自己的 Secrets 配置 `OPENAI_API_KEY`、`ALGOTOP_LLM_MODEL`。模型必须显式指定。不要把 key 发到聊天、表单、源码、URL 或 localStorage。界面只显示是否已配置、提供方和校验后的模型名。

控制台只允许官方 `https://api.openai.com/v1`；自定义端点被拒绝，即使原有 CLI 支持受信任自定义端点。实际调用沿用已有官方 `OpenAI(...).chat.completions.create(...)` adapter。此次未使用真实密钥、未执行收费请求；模型可用性、结构化输出兼容性、账单和在线提取质量均未验证。需自行配置提供方账户支出限制。

## 限制与安全边界

- JSON 请求 ≤600,000 bytes；材料 ≤512,000 UTF-8 bytes；规范化正文 ≤40,000 字符。超限失败，不静默截断。
- 导入解析子进程预算 10 秒；获取子进程 25 秒；真实提取子进程 40 秒，内部单次请求超时 30 秒、不重试。预算到期终止本地子进程；已送达提供方的请求不保证撤销或免计费。
- 最多 8 个 HTTP 工作线程；一次只处理一个状态操作；socket 读写空闲超时 5 秒。无后台队列、自动重试或计划任务。
- 所有路由严格 Host 检查，POST 要求同源 Origin + 随机 CSRF token + JSON。无 CORS、目录浏览、文件读写 API 或发布路由。
- 所有响应 no-store；CSP 禁止内联脚本、外部连接、图片、frame 和表单提交。不可信正文和模型输出仅通过 `textContent` 渲染。
- 原文仅在内存/工作子进程传递。抓取仅产生临时的元数据缓存，正常结束清理；硬终止可能留下无正文的临时元数据目录。访问日志不记录 URL、正文、密钥或 token。
- 这是同一台可信电脑上的单人本地工具，不是多租户服务；不能防御已经控制本机进程/浏览器的攻击者。

## 验证

```sh
python -m unittest discover -s tests -p 'test_local_console.py' -v
python -m unittest discover -s tools/collection -v
npm test
```

控制台协议测试不进行提供方网络调用；策略拒绝用例在实际访问网络之前停止。另由浏览器 QA 验证页面交互与下载。公开站文件保持不变。
