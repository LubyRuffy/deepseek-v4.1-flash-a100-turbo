# CLI

所有命令均从仓库根目录执行。Python 脚本的 `--help` 是其参数入口。

## Existing node launcher

```bash
pip install -r requirements.txt
python launch.py /existing/DeepSeek-V4.1-Flash --dry-run
python launch.py /existing/DeepSeek-V4.1-Flash --image deepseek-v41-sm80:local --port 8083
```

支持镜像、容器名、监听端口、显存比例和 dry-run。权重目录必须已经存在并
包含 `config.json`；dry-run 只打印 Docker 参数，不启动容器。

## Patch installation and verification

基础优化补丁仍由 `python patches/install.py` 使用其固定默认包路径安装。
Responses 身份补丁使用独立安装器，具体参数见
[runbook](native-responses-identity.md)。安装目标为含 `entrypoints/` 的 vLLM 包目录，不能指向 site-packages 父目录或模型权重目录。
只有已登记的完整源 profile 可以安装；发现混合或未知文件时必须调查，不能
绕过哈希校验。

## Router

```bash
python router/launch.py router/config.json --dry-run
python router/launch.py router/config.json
python router/adaptive_router.py router/config.json
```

router 使用独立依赖，默认只监听回环地址。完整配置和原有兼容边界见
[router README](../router/README.md)。

## Development and release

```bash
python3 -m pytest -q tests
python3 scripts/docs_check.py
make check
make version
make release
```

`make release` 是发布入口，须已取得相应发布授权。测试和文档检查通过不等于
生产部署完成。运行时模块测试与节点验收见 [TESTING](TESTING.md)。既有
benchmark 参数使用 [benchmark README](../benchmarks/README.md)。

相关功能：`F-110`、`F-120`、`F-140`、`F-150`。
