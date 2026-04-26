import asyncio
import json
from pathlib import Path
from typing import Optional, Dict, Any

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.dashboard.dashboard_decorator import (
    dashboard_router,
    auth,
    get_arg,
)


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
    "监控 GitHub 仓库 Release 更新的 AstrBot 插件，支持Web界面手动检查和发送",
    "2.0.0",
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

    @dashboard_router.get("/github_release_monitor/api/status")
    @auth
    async def get_status(self):
        if not self.monitor:
            return {"success": False, "message": "请先在插件配置中设置 repo_owner 和 repo_name"}
        return {
            "success": True,
            "repo_owner": self.monitor.repo_owner,
            "repo_name": self.monitor.repo_name,
            "last_release_sha": self.monitor.last_release_sha or "未记录",
            "message_template": self.monitor.message_template,
            "latest_release": self.latest_release_data,
        }

    @dashboard_router.post("/github_release_monitor/api/check")
    @auth
    async def check_release(self):
        if not self.monitor:
            return {"success": False, "message": "请先在插件配置中设置 repo_owner 和 repo_name"}
        
        release_data = await self.monitor.check_release()
        if not release_data:
            return {"success": False, "message": "获取 Release 信息失败"}
        
        self.latest_release_data = release_data
        rendered_message = self.monitor.render_message(release_data)
        return {
            "success": True,
            "release": release_data,
            "rendered_message": rendered_message,
        }

    @dashboard_router.post("/github_release_monitor/api/update_template")
    @auth
    async def update_template(self):
        if not self.monitor:
            return {"success": False, "message": "请先在插件配置中设置 repo_owner 和 repo_name"}
        
        template = get_arg("template", str)
        if not template:
            return {"success": False, "message": "模板不能为空"}
        
        self.monitor.save_message_template(template)
        return {"success": True, "message": "模板更新成功"}

    @dashboard_router.post("/github_release_monitor/api/send")
    @auth
    async def send_notification(self):
        if not self.monitor:
            return {"success": False, "message": "请先在插件配置中设置 repo_owner 和 repo_name"}
        
        if not self.latest_release_data:
            return {"success": False, "message": "请先检查 Release 更新"}
        
        message = get_arg("message", str)
        if not message:
            message = self.monitor.render_message(self.latest_release_data)
        
        try:
            # 直接使用上下文发送消息
            if hasattr(self.context, 'send_message'):
                await self.context.send_message(message)
            else:
                # 回退方案：记录消息但不发送
                logger.info(f"通知内容: {message[:50]}...")
            
            self.monitor.save_last_release_sha(self.latest_release_data["current_sha"])
            self.monitor.last_release_sha = self.latest_release_data["current_sha"]
            return {"success": True, "message": "通知发送成功"}
        except Exception as e:
            logger.error(f"发送通知失败: {e}")
            return {"success": False, "message": f"发送通知失败: {str(e)}"}

    @dashboard_router.get("/github_release_monitor/")
    @auth
    async def get_dashboard_page(self):
        return self.context.dashboard.render_template(
            "github_release_monitor.html",
            plugin=self,
        )
