import asyncio
import json
from pathlib import Path
from typing import Optional, Dict, Any

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


class GitHubReleaseMonitor:
    def __init__(
        self,
        repo_owner: str,
        repo_name: str,
        github_token: Optional[str] = None,
        data_path: Optional[Path] = None,
    ):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.github_token = github_token
        self.data_path = data_path or Path(__file__).parent / "data"
        self.data_path.mkdir(exist_ok=True)
        self.last_release_sha = self.load_last_release_sha()
        self.api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        self.message_template = self.load_message_template()

    def load_last_release_sha(self) -> Optional[str]:
        sha_file = self.data_path / ".last_release_sha"
        if sha_file.exists():
            with open(sha_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        return None

    def save_last_release_sha(self, sha: str):
        with open(self.data_path / ".last_release_sha", "w", encoding="utf-8") as f:
            f.write(sha)

    def load_message_template(self) -> str:
        template_file = self.data_path / "message_template.json"
        if template_file.exists():
            with open(template_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("template", "")
        default_template = (
            "🎉 {repo_name} 有新 Release！\n"
            "版本: {release_name}\n"
            "SHA: {current_sha}\n\n"
            "{release_body}\n\n"
            "查看详情: {release_url}"
        )
        self.save_message_template(default_template)
        return default_template

    def save_message_template(self, template: str):
        template_file = self.data_path / "message_template.json"
        with open(template_file, "w", encoding="utf-8") as f:
            json.dump({"template": template}, f, ensure_ascii=False, indent=2)
        self.message_template = template

    async def get_latest_release(self):
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        logger.error(f"请求失败: 404 - 仓库 {self.repo_owner}/{self.repo_name} 不存在或没有 Release")
                        return None
                    elif response.status == 403:
                        logger.error(f"请求失败: 403 - API 限制或 Token 无效")
                        return None
                    else:
                        logger.error(f"请求失败: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"请求异常: {e}")
            return None

    async def check_release(self) -> Optional[Dict[str, Any]]:
        logger.debug(f"检查 {self.repo_owner}/{self.repo_name} 的最新 Release...")

        release = await self.get_latest_release()
        if not release:
            return None

        current_sha = release.get("target_commitish", "")
        release_name = release.get("name", "未命名 Release")
        release_body = release.get("body", "暂无描述")
        release_url = release.get("html_url", "")

        is_new = self.last_release_sha != current_sha
        if is_new:
            logger.info(f"发现新 Release! SHA: {current_sha}")

        return {
            "is_new": is_new,
            "release_name": release_name,
            "current_sha": current_sha,
            "release_body": release_body,
            "release_url": release_url,
            "repo_name": self.repo_name,
        }

    def render_message(self, release_data: Dict[str, Any]) -> str:
        return self.message_template.format(**release_data)


@register(
    "github_release_monitor",
    "Your Name",
    "监控 GitHub 仓库 Release 更新的 AstrBot 插件，支持手动检查和发送",
    "2.1.0",
    "",
)
class GitHubReleaseMonitorPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}
        self.monitor: Optional[GitHubReleaseMonitor] = None
        self.latest_release_data: Optional[Dict[str, Any]] = None
        self._init_monitor()

    def _init_monitor(self):
        repo_owner = self.config.get("repo_owner")
        repo_name = self.config.get("repo_name")
        github_token = self.config.get("github_token")
        self.adapter_instance = self.config.get("adapter_instance", "all")

        if not repo_owner or not repo_name:
            logger.warning("请在插件配置中设置 repo_owner 和 repo_name")
            return

        data_path = Path(__file__).parent / "data"
        self.monitor = GitHubReleaseMonitor(
            repo_owner=repo_owner,
            repo_name=repo_name,
            github_token=github_token,
            data_path=data_path,
        )

    async def terminate(self):
        logger.info("GitHub Release Monitor 插件已停止")

    @filter.command("github_release_check")
    async def check_release_command(self, event: AstrMessageEvent):
        """检查 GitHub Release 更新"""
        if not self.monitor:
            yield event.plain_result("请先在插件配置中设置 repo_owner 和 repo_name")
            return

        yield event.plain_result("正在检查最新 Release...")
        release_data = await self.monitor.check_release()
        
        if not release_data:
            yield event.plain_result(f"获取 Release 信息失败，请检查：\n1. 仓库 {self.monitor.repo_owner}/{self.monitor.repo_name} 是否存在\n2. 仓库是否有 Release\n3. GitHub Token 是否有效（如果配置了）\n4. 网络连接是否正常")
            return

        self.latest_release_data = release_data
        message = self.monitor.render_message(release_data)
        
        status = "新 Release!" if release_data["is_new"] else "当前 Release"
        yield event.plain_result(f"✅ 检查完成！\n状态: {status}\n版本: {release_data['release_name']}\nSHA: {release_data['current_sha']}\n\n消息预览: {message[:100]}...")

    @filter.command("github_release_send")
    async def send_notification_command(self, event: AstrMessageEvent):
        """发送 GitHub Release 通知"""
        if not self.monitor:
            yield event.plain_result("请先在插件配置中设置 repo_owner 和 repo_name")
            return

        if not self.latest_release_data:
            yield event.plain_result("请先使用 github_release_check 检查 Release 更新")
            return

        message = self.monitor.render_message(self.latest_release_data)
        
        try:
            yield event.plain_result(message)
            self.monitor.save_last_release_sha(self.latest_release_data["current_sha"])
            self.monitor.last_release_sha = self.latest_release_data["current_sha"]
            yield event.plain_result("✅ 通知发送成功！")
        except Exception as e:
            logger.error(f"发送通知失败: {e}")
            yield event.plain_result(f"❌ 发送通知失败: {str(e)}")

    @filter.command("github_release_template")
    async def view_template_command(self, event: AstrMessageEvent):
        """查看消息模板"""
        if not self.monitor:
            yield event.plain_result("请先在插件配置中设置 repo_owner 和 repo_name")
            return

        template = self.monitor.message_template
        yield event.plain_result(f"📝 当前消息模板:\n\n{template}\n\n可用变量: {{repo_name}}, {{release_name}}, {{current_sha}}, {{release_body}}, {{release_url}}")

    @filter.command("github_release_template_set")
    async def set_template_command(self, event: AstrMessageEvent):
        """设置消息模板，格式: github_release_template_set [模板内容]"""
        if not self.monitor:
            yield event.plain_result("请先在插件配置中设置 repo_owner 和 repo_name")
            return

        template = event.message.content.split(" ", 1)
        if len(template) < 2:
            yield event.plain_result("请提供模板内容，格式: github_release_template_set [模板内容]")
            return

        template_content = template[1]
        self.monitor.save_message_template(template_content)
        yield event.plain_result("✅ 模板设置成功！")

    @filter.command("github_release_status")
    async def status_command(self, event: AstrMessageEvent):
        """查看监控状态"""
        if not self.monitor:
            yield event.plain_result("请先在插件配置中设置 repo_owner 和 repo_name")
            return

        status_msg = (
            "📊 GitHub Release 监控状态\n"
            f"仓库: {self.monitor.repo_owner}/{self.monitor.repo_name}\n"
            f"最后记录 SHA: {self.monitor.last_release_sha or '未记录'}\n"
            f"适配器实例: {self.adapter_instance}\n"
            f"消息模板: {self.monitor.message_template[:50]}..."
        )
        yield event.plain_result(status_msg)
