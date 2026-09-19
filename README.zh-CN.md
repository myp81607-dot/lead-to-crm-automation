# 表单咨询与联系人更新

[English](README.md) · [简体中文](README.zh-CN.md)

小型服务团队收到网站咨询后，需要保存原文、分配跟进人，并确认联系人哪一份资料是最新的。这个工具保留每次咨询的处理历史，同时按邮箱维护一条联系人记录。

表单或 n8n Webhook → 校验并分派 → 更新联系人，或留下明确的待处理事项。

[58 秒完整流程录像](docs/demo.webm) · [旧咨询复核演示](docs/review-update.webm) · [界面截图](docs/screenshots/02-output.png)。GitHub 提供录像下载入口，点击 **View raw** 后保存打开即可。第一段保留原版界面，接入和故障恢复行为不变；复核片段展示本轮界面和下面的修复。

这是使用虚构咨询的个人项目。本地 Python 与 SQLite CRM 无需账号或密钥即可运行；工作流已在 n8n 2.39.8 中实际导入并运行，包含定时重试，详见[安装与执行记录](n8n/README.md)。HubSpot 和可选模型接口未实连验证，通知只保存为草稿，不会发送。

适合据此定制一个表单到 CRM 的同步，或修复已有咨询流程。开始前需要一份样例输入、目标联系人字段、分派规则，以及获授权的测试环境。

![咨询历史与当前联系人资料并列显示](docs/screenshots/02-output.png)

## 在本机运行

安装 Python 3.12 或以上版本。[下载仓库 ZIP](https://github.com/myp81607-dot/lead-to-crm-automation/archive/refs/heads/main.zip)，解压后在该目录打开终端，不需要安装 Python 第三方包。

```sh
python app.py
```

打开 [localhost:8765](http://127.0.0.1:8765)，点击 **New inquiry → Fill sample → Submit inquiry**。也可以另开终端载入七条样例：

```sh
python demo.py
```

样例包含非法邮箱、尚未分类的咨询、模拟凭据失效，以及需要核对写入结果的咨询。重复执行命令会识别相同事件，不增加记录。数据保存在不会提交到 Git 的 `data/leads.db`；Ctrl+C 停止服务，`python app.py --db data/fresh.db` 可以换一个全新的数据库。

## 换成自己的输入和规则

把 [examples/lead.json](examples/lead.json) 复制为 `data/my-inquiry.json`，换成你有权处理的资料和咨询原文，选择服务类别、地区，并为每次新咨询填写新的 `event_id`。重试同一次投递时，保持 ID 和请求内容完全相同。

```sh
curl -X POST http://127.0.0.1:8765/api/leads -H "Content-Type: application/json" --data-binary @data/my-inquiry.json
```

Windows 使用 `curl.exe`，或采用 [operations.md](docs/operations.md) 中的 PowerShell 命令。修改 [rules.json](rules.json) 的团队名称后，再提交一条新咨询即可看到新分派。例如把 `"automation": "Workflow team"` 改为 `"automation": "Intake team"`，下一条自动化咨询会分给 Intake team；已有咨询历史中的旧分派不变。

如需通过 n8n 接收请求，按照[同机安装步骤](n8n/README.md)导入仓库内的工作流。它调用同一套 API：Python 负责去重和重试状态，n8n 提供 Webhook 和每分钟的到期处理触发。

## 遇到待处理事项时

| 界面状态 | 处理方式 |
| --- | --- |
| Needs review | 修正缺失或非法字段后提交，原始输入仍保留在历史中。 |
| Filed · contact unchanged | 同邮箱已有较新咨询完成更新，或其 CRM 结果还不确定。旧请求仍会分派和留档，但不会覆盖较新资料。可打开关联的新咨询或查看当前联系人。 |
| Retry scheduled | 等待到期，由 n8n 调度或 **Process due retries** 推进。每个事件的 CRM 步骤最多尝试三次。 |
| Verify result | **Verify CRM result** 读取 CRM，核对事件标记与字段。不匹配时保持未解决，不重复写入。 |
| Blocked | 先检查凭据、配置错误或重试次数，再决定下一步；无效凭据不会自动重试。 |

旧咨询待复核时，不会挡住新的有效咨询。稍后修正旧请求，也不代表要把它的联系人资料重新设为最新；资料顺序以收到咨询的先后为准，修正邮箱后碰到已有联系人时也如此。

## 实际检查过什么

本轮先复现了 `Old company / unsure → New company / automation → 只修旧咨询类别`。修复前联系人会退回 Old company；现在公司名、description 和事件 ID 仍对应较新咨询，旧请求被分派留档，CRM 写入次数为零。

在 Windows / Python 3.14.5 上，六项复核相关测试与两项既有顺序测试通过，覆盖改邮箱碰到新联系人、普通修正、另一邮箱、较新写入不确定、重启恢复和重试顺序。[测试输出](docs/test-results.txt)保留此前 23 项基线及本轮针对性结果。基线的 36 次合成提交产生 34 个独立事件、恢复后 29 个完成、5 个待复核和 27 个联系人；这是固定样例上的行为验证，不是生产效果或模型准确率。

```sh
python -m unittest discover -s tests -v
```

n8n 的实际执行、软件版本和复验命令见 [n8n/README.md](n8n/README.md)。本地模式下的超时与限流明确属于故障模拟；没有执行付费推理、真实 HubSpot 写入或真实消息发送。

## 接入外部 CRM 前

每个数据库只运行一个服务进程，供本机使用。本版没有公网部署、生产鉴权、多团队或数据保留策略，后端只监听回环地址，不应直接暴露为无鉴权的公网服务。

HubSpot adapter 会用所接受咨询的资料替换姓名、公司和 description，并在 description 中加入事件标记；不会分配 HubSpot owner。启用前应先确定字段映射和获授权测试账户。[运行与接口说明](docs/operations.md)列出了令牌环境变量、读回核对、失败状态和可选摘要模型的配置方式。

代码与小型 n8n 导出为本项目编写，开发使用 AI 辅助。公开 n8n 线索模板提供了流程参考，官方 n8n 和 HubSpot 文档提供了接口依据，未复制模板代码。详见[来源与许可证说明](docs/references.md)；原创代码使用 [MIT 许可证](LICENSE)。
