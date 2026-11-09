# 每日兴趣简报配置
基于guo-yichen/news-summary。上游README的Claude配置已过时，当前使用Kimi。

1. Settings → Secrets and variables → Actions → New repository secret，添加：

| 名称 | 值 |
|---|---|
| KIMI_API_KEY | Moonshot开放平台API密钥，不是聊天会员 |
| EMAIL_USER | 发件QQ邮箱地址 |
| EMAIL_PASSWORD | QQ邮箱SMTP授权码，不是登录密码 |
| EMAIL_TO | 收件邮箱，可与发件邮箱相同 |

2. Actions → Daily Summary → Run workflow → check：免费检查来源，不调用AI、不发邮件。Fork若提示启用工作流，先启用。
3. 填好密钥后选send，真实调用付费API并发邮件。核对收件箱和账单。
4. 在Variables添加DIGEST_ENABLED=true，才会每天北京时间08:00触发。执行可能延迟。改false暂停。

默认QQ发件（SSL 465）。Gmail发件可添加Variable SMTP_HOST=smtp.gmail.com并使用Gmail应用专用密码。
每次最多14篇候选、每篇3000字符、输出4000 token；一次模型调用，无自动重试。用量在日志。价格以Moonshot当期账单为准，不能套用DeepSeek费用。默认保留原项目moonshot-v1-128k，可用KIMI_MODEL变量修改。首次付费测试前确认账户模型可用与单价。

公开仓库不再提交新简报正文；全文留在邮箱。来源是初始候选，需check验证，并非全网搜索；缺少中大活动与完整中文本地来源。仅摘要或截断正文无法支持深度核验。
去重缓存保存7天内已处理候选链接；缓存被清理可能重复。不同链接的同一事件可能重复。邮件失败不会发布新缓存。SMTP接受但缓存保存失败，重跑可能重复投递。手动send会付费，不要反复点击。
