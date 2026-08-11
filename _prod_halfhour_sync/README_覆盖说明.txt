覆盖到: D:\deploy\testai_community_prod\
保持相对路径不变（整夹 backend\ 盖进去对应位置）。

1) 覆盖本包全部文件
2) 编辑生产 .env 增加:
   DINGTALK_PUSH_IDEMPOTENCY_ENABLED=false
   DINGTALK_WEEKLY_IDEMPOTENCY_ENABLED=false
3) cd D:\deploy\testai_community_prod\backend\scripts
   dir install_halfhour_push_test.*
   .\install_halfhour_push_test.cmd
4) 冒烟:
   $env:TM_PUSH_FORCE = "1"
   powershell -NoProfile -ExecutionPolicy Bypass -File .\wecom_push_halfhour_test.ps1

测完还原:
   .\restore_normal_push_schedule.cmd
   并把两个 IDEMPOTENCY 改回 true
