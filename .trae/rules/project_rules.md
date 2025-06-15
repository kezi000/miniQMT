在接下来的对话中，请严格遵循以下步骤：
# 任何情况下必需遵守:在回答问题后,不要说 "我已经修复了..." "我已经解决了..." "我已经完成了..."等类似的结论性回答,必须要调用 MCP mcp-feedback-enhanced等待我的回复反馈,直到接收到我的回答是"问题已经完美解决",这句话时,才结束本次对话.
任何步骤后必须用户反馈【包括意见、结束确认等】：调用`Terminal`工具执行`python3 -c "input('>>> ')"` 
首先分析出现哪几条错误,列出来,在逐步逐条解决。
1. 在任何流程、任务、对话进行时，无论是询问、回复、或完成阶段性任务，皆必须调用 MCP mcp-feedback-enhanced。
2. 每当收到用户反馈，若反馈内容非空，必须再次调用 MCP mcp-feedback-enhanced，并根据反馈内容调整行为。
3. 仅当用户明确表示「结束」或「不再需要交互」时，才可停止调用 MCP mcp-feedback-enhanced，流程才算结束。
4. 除非收到结束指令，否则所有步骤都必须重复调用 MCP mcp-feedback-enhanced。
5. 完成任务前，必须使用 MCP mcp-feedback-enhanced 工具向用户询问反馈。
6.Whenever you want to ask a question, always call the MCP mcp-feedback-enhanced .
7.Whenever you're about to complete a user request, call the MCP mcp-feedback-enhanced instead of simply ending the process. If the feedback is empty you can end the request and don't call the mcp in loop.
8. 如果我有发送图片、文档给你，或者请你查阅某个URL，你需要完整读取并理解其中内容。
9. 请整理我的命令并简述，确保你的理解和我的指令没有偏差。如果有疑惑进行第3步，如果没有，则跳过第3步进行第4步。
10. 将你的疑惑和不清楚的点列出来给我，我会回答你。
11. 简述你的解决方案和理由。
12.首先分析出现哪几条错误,列出来,在逐步逐条解决。
13. 用简体中文回复我,在生成代码时添加函数级注释。
