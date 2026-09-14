# 下载、缓存与分包的完整性

## 下载与清单身份

bundle 和 APK 共用下载状态机。只有完整响应才会原子替换目标文件；失败保留原来的完整文件。实际收到的字节数必须符合 HTTP 长度与范围声明。`fileSize` 的网络表示语义尚未确定，因此不把它与解密后的字节数混比。

`.part.json` 记录请求 URL、对象元数据、最终 URL、强 ETag、整体长度和已保存前缀的 SHA-256。只有记录与实际前缀一致，且存在强 ETag 或用户提供的完整摘要时，才能继续下载。强 ETag 通过 `If-Range` 发送。旧版没有身份记录的 `.part` 会重新下载；完整 `200` 响应会重启。错误范围、对象变化或 hash 不符会清理临时状态。`416` 只有在完整大小与用户提供的摘要均匹配时才能放行，否则重新完整下载。每个目标使用进程锁，阻止并发写入相同临时文件。

没有可信源摘要时，HTTP 长度、范围和 ETag 校验不能替代来源真实性证明；建议调用方提供 SHA-256。未知长度的完整关闭连接响应遵循 HTTP 的结束语义，无法证明服务端本来打算发送多少字节。

Manifest 会在下载前检查重复名称、本地名称、大小写和临时文件键碰撞。斜杠与双下划线别名只有全部元数据一致时才合并，包括显式缓存名和依赖；冲突定义报错。JSON 对象里的重复键也不能覆盖不同定义。

## Master 缓存与关联

缓存目录按规范化来源和可选快照标识的 SHA-256 隔离。缓存文件是带来源、表名、快照、原始 JSON 文本和 SHA-256 的完整记录，通过临时文件原子替换。旧版根目录中的 `<表名>.json` 缓存不参与新来源的命中。

默认冻结已缓存的表，同来源重复运行不自动联网更新。Python API 可显式选择快照或刷新：

```python
from core.master import Master

frozen = Master(source_url, cache_dir=cache_dir, snapshot="input-version")
refreshed = Master(source_url, cache_dir=cache_dir, snapshot="input-version", refresh=True)
```

CLI 使用默认快照；不同版本应使用含版本的来源 URL，或另一缓存目录。缓存不能给可变远端创造跨表事务；需要一致快照时，来源本身应固定到版本或提交。缓存损坏明确报错，显式刷新可以重新获取。

`Master.provenance`、`pull` 返回值与 `extraction-report.json` 的 `masterInputs` 记录实际读取表的来源、快照、hash 和本地读取、缓存命中、远程获取、缺失或失败状态。

单角色对话筛选区分已确认独立、已确认排除和未解析。缺失的条件或分组不会成为“不依赖家具”的证明。`excluded` 统计已确认排除；`unresolvedCount`、`unresolved` 和 `unresolvedTalks` 单独记录未解析数量、原因、talk ID 和原始关联键。

## 分包与发布

源、输出及变换 overlay 与输出不得重叠；检查会解析链接别名，且发生在输出写入前。输入路径先规范化和去重，再分组；根内 `models/../image.png` 变成 `image.png`，真正越界报错。

现存 blob 只有实际大小、hash、解码后大小与 hash 都正确才复用。损坏对象会重新编码并原子替换；每次发布前独立 verifier 会重新核对本次引用的磁盘内容。

分组包清单使用 `packages/<完整清单 SHA-256>.json`。一次构建先完成并校验全部包的版本、路径所有权、依赖和 blob，再写入 `catalogs/<catalog SHA-256>.json`，最后原子替换入口 `asset-packs.json`。旧 catalog 引用的包清单始终保留；读取、编码或写入失败不会改写旧包清单。入口切换完成后发生异常时，新入口已经指向完整的新版本。

```sh
python -m pack.groups --src extracted --out packages --version release-version
python -m pack.verify --out packages
python -m pack.gc --out packages --json
```

`pack.verify --out` 自动识别 grouped catalog，并验证所有保留的历史 catalog；独立 manifest 仍可通过 `--manifest` 检查。schema 随安装包提供，`--schema` 仅用于覆盖。未被当前或历史 catalog 引用的 blob 单独列为 GC 候选。`pack.gc --out` 以所有保留代的引用并集计算候选，**只报告，不删除**。`--old/--new` 是两个独立 manifest 的差集，不可用来回收共享的 grouped blob store。

原子替换保证普通文件系统上的进程可见性；该流程不承诺断电后目录元数据的持久化，也不能把对象存储中的多次上传变成事务。远程发布需要先上传不可变包清单和 blob，再切换 catalog。

## 安装与验证

wheel 和 sdist 显式携带三份 TOML、两份 MJS 和 manifest schema。默认 gzip 编解码使用标准库；Brotli 需要 Python `brotli` 或 Node.js，MJS 回退脚本随包分发。glTF 变换额外需要 `@gltf-transform/core`、`@gltf-transform/extensions`、`@gltf-transform/functions` 和 `meshoptimizer`，按 `transforms.toml` 选择版本，并用 `MOLY_QUANT_DIR` 指定依赖目录。音频解码程序仍由调用方提供。

完整安装验证在源码树外构建 sdist/wheel、创建全新虚拟环境、安装 wheel 及依赖，并运行 CLI help、合成独立分包、两代 grouped 分包、独立 verifier 和 GC 检查：

```sh
python -m pip install build
python tests/check_distribution.py --work-dir ../distribution-check
python -m pytest -q
```

工作目录必须尚不存在。安装验证需要访问配置的 Python 包索引，不需要游戏网络端点或真实资产。故障注入测试使用回环 HTTP、合成 JSON 和合成字节；它们不代替真实提取语料或下游视觉验收。

| 审计项 | 回归覆盖 |
| --- | --- |
| ROOT-01 / ROOT-02 | 完整及截短响应、合法/错误续传、ETag 变化、hash 失败、416 恢复、APK 与并发锁 |
| ROOT-03 | 等长损坏、截短 blob、删除旧清单后重建、磁盘写入损坏与复用 |
| ROOT-04 | 读取、压缩、blob、包清单、历史 catalog、入口切换前后故障；旧代与 GC 引用 |
| ROOT-05 | 回环双来源、冻结/刷新、快照隔离、缓存损坏、缓存原子写入与输入来源报告 |
| ROOT-06 | 完整 sdist/wheel 资源检查、干净安装、源码树外 CLI 与分包 |
| ROOT-07 | 重复定义、相同别名合并、大小写/临时文件键碰撞、JSON 重复键 |
| ROOT-08 / ROOT-09 | 根内父级引用、GLB 相对 URI、越界、源/输出/overlay 重叠及链接别名 |
| ROOT-10 | 缺 condition、缺类型、缺 group、悬空 unit group，及已有家具/非家具对照 |
