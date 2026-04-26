import asyncio
import time
import os
from pathlib import Path
from typing import Optional

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


class GitHubReleaseMonitor:
    def __init__(
        self,
        repo_owner: str,
        repo_name: str,
        check_interval: int = 60,
        github_token: Optional[str] = None,
        data_path: Optional[Path] = None,
    ):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.check_interval = check_interval
        self.github_token = github_token
        self.data_path = data_path or Path(__file__).parent / "data"
        self.data_path.mkdir(exist_ok=True)
        self.last_release_sha = self.load_last_release_sha()
        self.api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._new_release_callback = None

    def load_last_release_sha(self) -> Optional[str]:
        sha_file = self.data_path / ".last_release_sha"
        if sha_file.exists():
            with open(sha_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        return None

    def save_last_release_sha(self, sha: str):
        with open(self.data_path / ".last_release_sha", "w", encoding="utf-8") as f:
            f.write(sha)

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

    def set_new_release_callback(self, callback):
        self._new_release_callback = callback

    async def check_release(self):
        logger.debug(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 检查 {self.repo_owner}/{self.repo_name} 的最新 Release..."
        )

        release = await self.get_latest_release()
        if not release:
            return

        current_sha = release.get("target_commitish", "")
        release_name = release.get("name", "未命名 Release")
        release_body = release.get("body", "暂无描述")
        release_url = release.get("html_url", "")

        if self.last_release_sha != current_sha:
            logger.info(f"发现新 Release! SHA: {current_sha}")

            if self._new_release_callback:
                await self._new_release_callback(
                    release_name=release_name,
                    current_sha=current_sha,
                    release_body=release_body,
                    release_url=release_url,
                )

            self.last_release_sha = current_sha
            self.save_last_release_sha(current_sha)
        else:
            logger.debug("暂无新 Release")

    async def _monitor_loop(self):
        while self._running:
            await self.check_release()
            await asyncio.sleep(self.check_interval)

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._monitor_loop())
            logger.info(
                f"开始监听 {self.repo_owner}/{self.repo_name} 的 Release 更新，检查间隔: {self.check_interval} 秒"
            )

    def stop(self):
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
                self._task = None
            logger.info(
                f"停止监听 {self.repo_owner}/{self.repo_name} 的 Release 更新"
            )


@register(
    "github_release_monitor",
    "Your Name",
    "监控 GitHub 仓库 Release 更新的 AstrBot 插件",
    "1.0.0",
    "",
)
class GitHubReleaseMonitorPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.monitor: Optional[GitHubReleaseMonitor] = None
        self._init_monitor()

    def _init_monitor(self):
        config = self.config
        repo_owner = config.get("repo_owner")
        repo_name = config.get("repo_name")
        check_interval = config.get("check_interval", 60)
        github_token = config.get("github_token")

        if not repo_owner or not repo_name:
            logger.warning("请在插件配置中设置 repo_owner 和 repo_name")
            return

        data_path = Path(__file__).parent / "data"
        self.monitor = GitHubReleaseMonitor(
            repo_owner=repo_owner,
            repo_name=repo_name,
            check_interval=check_interval,
            github_token=github_token,
            data_path=data_path,
        )
        self.monitor.set_new_release_callback(self._on_new_release)
        self.monitor.start()

    async def _on_new_release(
        self, release_name: str, current_sha: str, release_body: str, release_url: str
    ):
        message = (
            f"🎉 {self.monitor.repo_name} 有新 Release！\n"
            f"版本: {release_name}\n"
            f"SHA: {current_sha}\n\n"
        )
        if release_body:
            message += f"{release_body}\n\n"
        if release_url:
            message += f"查看详情: {release_url}"

        broadcast_platform = self.config.get(
            "broadcast_platform", "all"
        )
        await self._broadcast_message(message, broadcast_platform)

    async def _broadcast_message(self, message: str, target: str):
        try:
            yield self.plain_result(message)
            logger.info(f"已发送 Release 更新通知: {message[:50]}...")
        except Exception as e:
            logger.error(f"发送通知失败: {e}")

    @filter.command("github_release_check")
    async def check_now(self, event: AstrMessageEvent):
        """立即检查 GitHub Release 更新"""
        if not self.monitor:
            yield event.plain_result("请先在插件配置中设置 repo_owner 和 repo_name")
            return

        yield event.plain_result("正在检查最新 Release...")
        await self.monitor.check_release()

    @filter.command("github_release_status")
    async def status(self, event: AstrMessageEvent):
        """查看监控状态"""
        if not self.monitor:
            yield event.plain_result("请先在插件配置中设置 repo_owner 和 repo_name")
            return

        status_msg = (
            f"GitHub Release 监控状态\n"
            f"仓库: {self.monitor.repo_owner}/{self.monitor.repo_name}\n"
            f"检查间隔: {self.monitor.check_interval} 秒\n"
            f"最后检查 SHA: {self.monitor.last_release_sha or '未记录'}"
        )
        yield event.plain_result(status_msg)

    async def terminate(self):
        if self.monitor:
            self.monitor.stop()
        logger.info("GitHub Release Monitor 插件已停止")

