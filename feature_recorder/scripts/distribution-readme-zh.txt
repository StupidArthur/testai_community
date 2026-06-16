功能录制 — 使用说明

【重要】解压后再运行
1. 右键 feature-recorder-win64.zip →「全部解压缩」
2. 解压到较短路径，例如 C:\feature-recorder（避免路径过长导致 node 未解压完整）
3. 若 zip 来自浏览器下载，先在属性里勾选「解除锁定」再解压
4. 确认解压目录内同时存在：
   - feature-recorder.cmd
   - node\node.exe
   - app\app.bundle.cjs
   - chrome-win64\chrome.exe

【启动】
双击 feature-recorder.cmd，浏览器打开 http://localhost:3000

【录制】
1. 配置被测 URL 并开始录制
2. 关闭浏览器窗口结束录制
3. 在 output\run_* 目录查看结果；录制结束后会自动生成同名的 run_*.zip

【交给 AI 翻译】
下载或打开 output 目录下的 run_*.zip，在 TestAI Community 工具集 → AI 翻译 上传
