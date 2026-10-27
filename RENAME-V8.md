# AlgoWen · 算问集：命名迁移与验收

## 已在本地实现

- 公开页面、浏览器标题采用 **AlgoWen · 算问集**；新进度文件名为 `algowen-progress-YYYY-MM-DD.json`。
- 有意保留浏览器键 `algotop-v1`、备份 `version: 1`、题目 ID、别名映射及 `#question=旧题号` 路由。不要全局替换兼容键或历史 ID。
- 旧 `algotop-progress-*.json` 文件仍可导入；文件名不参与校验。保留不在当前题库内的历史笔记；同题导入覆盖前仍需用户确认。
- 静态资源保持相对路径，可以部署在 `/algowen/` 或原路径，无需改写题库或打包绝对地址。
- `npm run build` 仍只输出 8 个公开运行文件到 `_site/`。本地控制台、采集器、私有审核材料、环境变量和密钥不得放入 Pages。

## 发布决策：仓库地址和网站地址不是同一回事

目标仓库为 `dqdallen/algowen`；预期项目站路径为 `https://dqdallen.github.io/algowen/`。**这只是目标，不是已上线声明。**

GitHub 明确说明：重命名仓库会重定向多数仓库链接，但**项目 Pages 地址不属于自动重定向范围**。不要把 Git 仓库重定向当作旧站链接保活。[GitHub 仓库改名说明](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)

发布负责人应根据已有仓库状态择一执行，不自动新建同名仓库：

1. 保留 `algotop` 旧仓库和旧站，在新 `algowen` 发布后，将旧站改成保留 `location.search + location.hash` 的跳转页；需要单独审核两处发布。旧 Git 仓库此时仍存在，不会自动成为新仓库的重定向。
2. 直接改名旧仓库，保留仓库历史与 GitHub 重定向；另行解决旧 Pages 路径。不要为了恢复旧站而直接重建同名仓库，避免破坏旧仓库地址的重定向。

无论哪种方案，先验证新站，再更改旧站；旧站跳转仅带查询和 hash，不在 URL 中携带学习数据。需要改自定义域名时，另行核对 DNS、HTTPS 和跨域进度迁移。

## 学习记录迁移边界

`localStorage` 按 origin（协议、域名、端口）隔离，不按 URL 路径隔离。因此在同一浏览器配置中，从 `https://dqdallen.github.io/algotop/` 到 `https://dqdallen.github.io/algowen/`，保留原键即可读取进度。不同浏览器、隐私模式、设备、端口或自定义域名不会自动共享：先在旧站导出，再在新站导入。不要清除站点数据来解决缓存问题；可先普通刷新或强制刷新。

发布前必须在旧站导出备份。旧站和新站同 origin 时共享同一进度键，互相修改会影响同一份数据；这不是云同步。多标签页同时编辑时以最后写入为准，避免同时编辑。

## 自动验证

```sh
npm test
npm run validate:data
npm run build
python -m unittest discover -s tools/collection -p 'test_*.py'
python -m unittest discover -s tests -p 'test_*.py'
```

`tests/rename-v8.test.js` 实际启动应用并验证：旧键读取、旧题号 hash 打开、别名归并、旧笔记/已移出题库笔记保留、新导出名称、旧版备份导入，以及写回仍使用旧键。它是 Node DOM 桩测试，不替代实际浏览器/线上验收。

## 用户手工验收清单

- [ ] 旧站导出一份真实备份；记下一题收藏、掌握状态和笔记。不要在聊天或公共仓库上传私人笔记。
- [ ] 同浏览器打开新站，确认记录和笔记仍在；若换域名/设备，手动导入备份。
- [ ] 打开旧收藏夹中的 `#question=...` 链接，确认跳转后题目正确；旧站链接应实际保留 hash，不只验证首页。
- [ ] 在新站修改一题、刷新，确认保存；导出并在另一浏览器导入，确认旧版与新版备份均能使用。
- [ ] 桌面和手机检查品牌、筛选、搜索、收藏、练习、答案与来源链接；键盘 Esc 关闭详情、Tab 可达导入导出按钮。
- [ ] 新站 HTTP 与 JS/CSS/JSON 加载成功，无控制台错误；旧站、仓库旧链接分别实测，不混为一项。
- [ ] 仅部署 `_site/`：确认站点无法访问 `.env`、`.collection/`、`.local-review/`、`local-console/`、`tools/` 或私人笔记。

遇到迁移问题先保留原备份和原浏览器数据，停止重复覆盖导入；回滚静态文件无需清空 `algotop-v1`。

## CI 运行时迁移（已暂存，线上运行待验收）

`.github/workflows/pages.yml` 已固定到 `ubuntu-24.04`，应用 Node 24；保留 main push / 手工触发、原 permissions/concurrency/environment、测试 → 数据审计 → 构建 → Pages 发布顺序。没有定时采集工作流。checkout 不持久化凭据，setup-node 显式关闭自动缓存，产物仍仅 `_site/`。

官方发行标签逐个点击到完整 commit，并读取该 SHA 的 `action.yml` 验证运行时/输入（2026-10-27）：

| Action | 发行版 | 完整 SHA |
|---|---|---|
| [checkout](https://github.com/actions/checkout/releases/tag/v5.0.1) | v5.0.1 | `93cb6efe18208431cddfb8368fd83d5badbf9bfd` |
| [setup-node](https://github.com/actions/setup-node/releases/tag/v5.0.0) | v5.0.0 | `a0853c24544627f65ddf259abe73b1d18a591444` |
| [configure-pages](https://github.com/actions/configure-pages/releases/tag/v6.0.0) | v6.0.0 | `45bfe0192ca1faeb007ade9deae92b16b8254a0d` |
| [upload-pages-artifact](https://github.com/actions/upload-pages-artifact/releases/tag/v5.0.0) | v5.0.0 | `fc324d3547104276b827a68afc52ff2a11cc49c9` |
| [deploy-pages](https://github.com/actions/deploy-pages/releases/tag/v5.0.1) | v5.0.1 | `368f82528645a54fb793d4d04e342629a3f51346` |

以上四个 JS Action 均声明 `runs.using: node24`。Pages 上传为组合 Action，v5 内部固定 `upload-artifact@bbbca2ddaa5d8feaa63e36b76fdaad77386f024f`（v7.0.0），也使用 Node24；没有停留在内部仍使用旧上传 Action 的 Pages 上传 v4。显式 `include-hidden-files: false`，先打包公开目录再上传 `artifact.tar`，保留默认 `github-pages` 名称；内部上传仍使用默认 `archive: true`，不切换 v7 的无归档模式。[组合 Action 定义](https://raw.githubusercontent.com/actions/upload-pages-artifact/fc324d3547104276b827a68afc52ff2a11cc49c9/action.yml)、[内部上传定义](https://raw.githubusercontent.com/actions/upload-artifact/bbbca2ddaa5d8feaa63e36b76fdaad77386f024f/action.yml)

固定 Ubuntu 24.04 避免 ubuntu-latest 后续迁移改变系统版本，不代表镜像内容永久冻结。[官方镜像说明](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md)

本地 Node 24 已执行测试/构建，YAML 已解析并检查触发器、权限和步骤；`tests/workflow-v8.test.js` 固定安全边界和官方 SHA。**本地验证不等于 GitHub 部署成功**：发布后还需等待真实 Actions 构建部署、检查运行时警告、产物内容及 Pages URL。没有本地执行第三方 Action 的远程发布逻辑。
