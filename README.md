# 本模块基于[retr0-init的模板](https://github.com/retr0-init/Discord-Bot-Framework-Module-Template)制作，可加载并运行在[retr0-init开发的kernal](https://github.com/retr0-init/Discord-Bot-Framework-Kernel)中

## 本模块功能：

- 为大舞台文章辩论比赛提供竞猜功能
- 如有需要也可为比赛添加投票功能

## 操作说明：

- 使用/bet setup_competition命令，bot会自动在bet_utils.COMPETITION_GUILD_ID和bet_utils.COMPETITION_FORUM_CHANNEL_ID指定的Guild中的Forum Channel内发出一活动控制专用贴，贴子内容包括若干控制按钮，分别用于参与人员领取竞猜代币以及管理人员管理赛事流程。