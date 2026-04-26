# GitHub Release 监控插件

这是一个为 AstrBot 开发的 GitHub Release 监控插件，支持手动检查 GitHub 仓库的 Release 更新并发送通知。

## 功能特性

- ✅ 手动检查 GitHub 仓库的最新 Release
- ✅ 支持自定义消息模板
- ✅ 手动触发发送通知
- ✅ 查看监控状态
- ✅ 支持 GitHub Token 认证（提高 API 请求限制）

## 安装方法

1. 克隆或下载本仓库到 AstrBot 的插件目录
2. 确保安装了必要的依赖：`aiohttp>=3.8.0`
3. 在 AstrBot 插件管理页面启用该插件

## 配置方法

在插件配置页面填写以下信息：

| 配置项 | 类型 | 描述 | 示例 |
|-------|------|------|------|
| `repo_owner` | 字符串 | GitHub 仓库所有者 | Soulter |
| `repo_name` | 字符串 | GitHub 仓库名称 | AstrBot |
| `github_token` | 字符串（可选） | GitHub Token，用于提高 API 请求限制 | ghp_xxxxxxxxxxxx |

## 使用命令

### 1. 检查 GitHub Release 更新

```
github_release_check
```

**功能**：检查指定 GitHub 仓库的最新 Release 信息。

**返回**：
- 检查状态
- 版本信息
- SHA 值
- 消息预览

### 2. 发送 GitHub Release 通知

```
github_release_send
```

**功能**：发送最新的 Release 通知。

**注意**：使用此命令前需要先使用 `github_release_check` 检查 Release 更新。

### 3. 查看消息模板

```
github_release_template
```

**功能**：查看当前的消息模板。

**返回**：
- 当前消息模板内容
- 可用变量列表

### 4. 设置消息模板

```
github_release_template_set [模板内容]
```

**功能**：设置自定义的消息模板。

**参数**：
- `[模板内容]` - 自定义的消息模板，支持以下变量：
  - `{repo_name}` - 仓库名称
  - `{release_name}` - Release 名称
  - `{current_sha}` - SHA 值
  - `{release_body}` - Release 描述
  - `{release_url}` - Release 链接

**示例**：
```
github_release_template_set 🎉 {repo_name} 发布了新版本！\n版本: {release_name}\n详情: {release_url}
```

### 5. 查看监控状态

```
github_release_status
```

**功能**：查看当前监控状态。

**返回**：
- 仓库信息
- 最后记录的 SHA 值
- 消息模板预览

## 消息模板示例

### 默认模板
```
🎉 {repo_name} 有新 Release！
版本: {release_name}
SHA: {current_sha}

{release_body}

查看详情: {release_url}
```

### 简洁模板
```
📣 {repo_name} 新版本发布！
版本: {release_name}
链接: {release_url}
```

## 常见问题

### 1. 检查 Release 失败

**可能原因**：
- 网络连接问题
- GitHub API 限制
- 仓库不存在
- 仓库没有 Release
- Token 无效

**解决方案**：
- 检查网络连接
- 配置有效的 GitHub Token
- 确认仓库路径正确
- 选择一个有 Release 的仓库，或为当前仓库创建 Release
- 测试配置：可以使用 `Microsoft/vscode` 等有 Release 的仓库来测试插件是否正常工作

### 2. 发送通知失败

**可能原因**：
- 未先执行 `github_release_check`
- 消息模板语法错误
- 权限问题

**解决方案**：
- 先执行 `github_release_check` 检查 Release
- 检查消息模板格式
- 确保机器人有发送消息的权限

## 版本历史

- **2.1.0** - 移除 Web 界面，改为命令行接口
- **2.0.0** - 添加 Web 界面支持
- **1.0.0** - 初始版本

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个插件！

## 许可证

MIT License
