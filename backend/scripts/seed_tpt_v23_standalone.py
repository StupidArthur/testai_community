# -*- coding: utf-8 -*-
r"""
TPT v2.3 产品包需求导入（单文件零依赖版）。

仅依赖 Python 标准库（sqlite3/uuid/datetime/shutil/os/sys），
无需 openpyxl、sqlalchemy、python-dotenv 等第三方包；
41 条 SR 数据内嵌于本文件 SRS 列表。

幂等：自动加列 → 备份库 → 清空 TPT 项目旧数据 → 写入41条 SR（含全部扩展字段）。
验证人按 users.real_name 精确匹配；匹配不到（如“刘豪”）自动记入 remark。

用法（backend 目录下执行）：
    python scripts\seed_tpt_v23_standalone.py
    （或指定 Python 解释器绝对路径）
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

PROJECT_NAME = "TPT v2.3 产品包"
PROJECT_DESC = "TPT v2.3 产品包需求（41条SR全量导入）"
LEAD_USERNAME = "zhengzhifang"

CANDIDATES = [
    r"D:\testai_community_prod\backend\database_prod.sqlite",
    r"D:\testai_community_prod\backend\database.sqlite",
    r"D:\deploy\testai_community_prod\backend\database_prod.sqlite",
    r"D:\deploy\testai_community_prod\backend\database.sqlite",
]

NEW_COLS = [
    ("sr_code", "TEXT NOT NULL DEFAULT ''"),
    ("ir_codes", "TEXT NOT NULL DEFAULT ''"),
    ("module", "TEXT NOT NULL DEFAULT ''"),
    ("req_type", "TEXT NOT NULL DEFAULT ''"),
    ("priority", "TEXT NOT NULL DEFAULT ''"),
    ("change_flag", "TEXT NOT NULL DEFAULT ''"),
    ("acceptance_criteria", "TEXT NOT NULL DEFAULT ''"),
    ("verifier_id", "INTEGER"),
    ("verified_at", "DATE"),
    ("verify_result", "TEXT NOT NULL DEFAULT ''"),
    ("remark", "TEXT NOT NULL DEFAULT ''"),
]

# ============ 41 条 SR 数据（字段顺序见下方 INSERT） ============
# 字段：sr_code, ir_codes, domain, module, title, requirement,
#       req_type, priority, change_flag, acceptance_criteria,
#       verifier_name, verified_at, verify_result, remark
SRS = [
    ('SR-TPT-00001', 'IR-TPT-00012', 'TPT平台', '数据中心', '智能问数功能增强',
     '智能问数接入预测数据\n智能问数接入模拟优化数据\n基于第三方系统注册生成skills，实现“问数2.0 + skills ”的通用问数能力',
     '功能', '高', '原始', '', '刘佳', None, '', ''),
    ('SR-TPT-00002', 'IR-TPT-00009，IR-TPT-00011，IR-TPT-00013', 'TPT平台', '数据中心', '数据中心功能增强',
     '采集器支持信创\nPA层软件及第三方系统的接入\n数据采集中断的报警通知\n存储\\查询（VxBase作为存储组件接入数据中心，支持结构化位号存储等常规功能，完成第一阶段联调）\n异常信息监控界面展示\n下写任务的统一管理\n支持一体机备份迁移；支持支持双机冗余热备\n国际化',
     '功能', '高', '原始', '', '顾靖', None, '', ''),
    ('SR-TPT-00003', 'IR-TPT-00016', 'TPT平台', '基础设施', '微服务功能增强',
     '具备一体化安装部署工具，支持对TPT相关服务进行统一管理\n具备补丁包更新功能，能够快捷完成后续升级更新\n具备回滚功能，仅支持回滚到升级前一个版本\n具备日志功能，记录补丁包更新升级及版本回滚操作\n具备授权狗配置界面\n运行时微服务基于现有产品体系系统重构\n国际化：一体化安装部署工具',
     '功能', '高', '原始', '', '刘义淑', None, '', ''),
    ('SR-TPT-00004', 'IR-TPT-00015', 'TPT平台', '基础设施', '计算引擎功能增强',
     '计算引擎提供单worker最大CPU及内存资源指标\n计算引擎TPT对传统机器学习算法支持CPU训练\n计算引擎在910C上完成集群训练测试\n单个算法实现在线数据推理和离线数据推理\nDAG在RAY上实现硬件亲和性技术研究',
     '功能', '高', '原始', '', '丁乔', None, '', ''),
    ('SR-TPT-00005', 'IR-TPT-00015', 'TPT平台', '基础设施', '算子优化功能增强',
     '研究数据预处理算法从CPU计算模式迁移到GPU/NPU计算模式相关技术\n时序模型在沐曦 C500上适配，并完成计算图的优化及算子的优化\n时序模型天数 智凯100上适配，并完成计算图的优化及算子的优化\n时序模型BW100上适配，并完成计算图的优化及算子的优化',
     '功能', '高', '原始', '', '丁乔', None, '', ''),
    ('SR-TPT-00006', 'IR-TPT-00015', 'TPT平台', '基础设施', '系统硬件适配功能增强',
     '非标便携算力机批量适配及底层验证交付\n沐曦C500底层操作系统、驱动、云原生及计算引擎适配\n天数智凯100底层操作系统、驱动、云原生及计算引擎适配\nBW100底层操作系统、驱动、云原生及计算引擎适配',
     '功能', '高', '原始', '', '刘义淑', None, '', ''),
    ('SR-TPT-00007', 'IR-TPT-00015', 'TPT平台', '基础设施', '云原生技术功能增强',
     '从操作系统内核获取系统实时资源\n评估应用层监控策略',
     '功能', '高', '原始', '', '刘义淑', None, '', ''),
    ('SR-TPT-00008', 'IR-TPT-00013', 'TPT平台', '基础设施', '国际化适配',
     '云化资源&海外访问问题',
     '功能', '高', '原始', '', '张莹', None, '', ''),
    ('SR-TPT-00009', 'IR-TPT-00002，IR-TPT-00003，IR-TPT-00009，IR-TPT-00017', 'TPT平台', '基础能力', '我的Agent功能增强',
     '创建自主规划Agent\nSKILL创建管理调试\n一个自主规划agent支持创建多个定时任务\n明确内置tool列表与skill列表\nagent、skill运行的安全、权限约束',
     '功能', '高', '原始', '', '朱婷卓', None, '', ''),
    ('SR-TPT-00010', 'IR-TPT-00005，IR-TPT-00009', 'TPT平台', '基础能力', '我的应用功能增强',
     '应用支持关联自主Agent并对话\n支持基于SKILL（前端样式和组件）生成应用大屏',
     '功能', '高', '原始', '', '朱婷卓', None, '', ''),
    ('SR-TPT-00011', 'IR-TPT-00002，IR-TPT-00003', 'TPT平台', '基础能力', '我的对话功能增强',
     '我的对话具备不同模式满足不同需求\n支持基于仿真对象自动化调试迭代\n支持创建、运行python脚本',
     '功能', '高', '原始', '', '朱婷卓', None, '', ''),
    ('SR-TPT-00012', 'IR-TPT-00006，IR-TPT-00014', 'TPT平台', '基础能力', '平台基本能力功能增强',
     '国际化\nTPT教育版方案设计\nbasf安全评测\n工厂模型统一组态\n系统管理功能增强\n提示词统一管理\n移动端',
     '功能', '高', '原始', '', '张莹', None, '', ''),
    ('SR-TPT-00013', 'IR-TPT-00006，IR-TPT-00008', 'TPT平台', '六大能力', 'SCOPE能力功能增强',
     '算法排队超时交互功能\n实现Agent下写逻辑的统一（目前没有），支持Agent下写（分别下写）\n在线运行Agents的统一性能监控与管理\n支持大文件和性能问题（SAAS支持 1个G传输）\n模型自适应更新功能\n模型评价与统计分析\n新增设备评估Agent，具备设备健康评估能力',
     '功能', '高', '原始', '', '叶学莉', None, '', ''),
    ('SR-TPT-00014', 'IR-TPT-00010，IR-TPT-00007', 'TPT平台', 'LLM', 'LLM能力功能增强',
     '记忆机制设计\n上下文管理/压缩\n边云协同\n生成报告与文档（方案撰写专家）\n数据解析和标注',
     '功能', '高', '原始', '', '朱婷卓', None, '', ''),
    ('SR-TPT-00015', 'IR-TPT-00001，IR-TPT-00004', '智能控制Agents', '智能控制', '智能控制融合',
     'python脚本在线运行阶段功能优化；\n模型辨识功能优化：\n敏捷控制组态期功能完善：高级功能算法快补充；仿真功能接入；\n支持arm及x86本版本，支持K8S统一安装部署\n智能步进在线运行阶段功能优化及完善；\n在组态阶段增加仿真播放功能，完成开发及测试，提升问题排查定位的效率.\nDataHub对接取数功能完善，支持缓存数据，同时缓存不足时直接数据源取数',
     '功能', '高', '原始', '', None, None, '', '验证人：刘豪'),
    ('SR-TPT-00016', 'IR-TPT-00001，IR-TPT-00004', '智能控制Agents', '操作导航', '操作导航融合',
     'TPT融合我的应用，页面风格优化同TPT一致\nDataHub数据源接入\n支持x86版本，支持K8S统一CICD安装部署\n一键开停车',
     '功能', '高', '原始', '', '覃霜', None, '', ''),
    ('SR-TPT-00017', 'IR-TPT-00001，IR-TPT-00004', '回路优化Agents', '回路优化', '回路优化融合',
     '回路预设agent\n回路优化agent\n支持arm及x86版本，支持K8S统一CICD安装部署\nskill能力封装（TPT+问数）\nTPT融合我的应用，页面风格优化同TPT一致',
     '功能', '高', '原始', '', '姜静', None, '', ''),
    ('SR-TPT-00018', 'IR-TPT-00001，IR-TPT-00004', '报警管理Agents', '报警管理', '报警管理融合',
     'TPT融合我的应用，页面风格优化同TPT一致\nDataHub数据源接入\nskill能力封装（TPT+问数）\n支持x86版本，支持K8S统一CICD安装部署\n报警治理agent',
     '功能', '高', '原始', '', '孙厚凯', None, '', ''),
    ('SR-TPT-00019', 'IR-TPT-00018，IR-TPT-00001，IR-TPT-00004', '设备健康监测Agents/设备诊断Agents', 'TPT融合', '设备健康监测TPT融合',
     'TPT中间件增加emqx和elasticsearch\n设备健康PRIDE统一到TPT的CICD\n设备健康PRIDE统一使用TPT中间件（postgresql、emqx、elasticsearch、nacos、minio、redis）\nTPT DataHub支持NeuroLink数据采集\n仪控设备健康Agent基于TPT能力适配(应用注册、DataHub数据、人员体系、系统编码等)\n动设备健康Agent基于TPT能力适配(应用注册、DataHub数据、人员体系、系统编码等)',
     '功能', '高', '原始', '', '袁小君', None, '', ''),
    ('SR-TPT-00020', 'IR-TPT-00006', 'utilities Agents', '能力提升', '软测量能力',
     '实时优化调度能力；新增连续装置软测量能力；开展半间歇/间歇装置质量在线评估能力开发',
     '功能', '高', '原始', '', '张莹', None, '', ''),
    ('SR-TPT-00021', 'IR-TPT-00018，IR-TPT-00001，IR-TPT-00004', '设备健康监测Agents/设备诊断Agents', 'AI能力提升', 'AI能力提升需求',
     '设备健康相关业务和指标类数据接口注册到TPT智能问数\nSkill能力封装',
     '功能', '高', '原始', '', '袁小君', None, '', ''),
    ('SR-TPT-00022', 'IR-TPT-00019，IR-TPT-00001', '计划调度优化Agents', '国产化', '国产化改造',
     'Assay数据管理\n字典管理\n日志管理（业务操作）\n模型管理库\n模型-基础设定\n模型-基础编码\n流程管理\n模型-供需约束\n模型-能力约束\n模型-流量约束\n模型-性质约束\n模型-性质传递\n常减压装置\n二次装置\n混分器装置\n调合器装置\n乙烯装置\n公用工程装置\n组分分离器\n强制平衡\n性质初值\n计算-计划优化参数校验封装\n计算-计划优化\n计算-配置\n计算-日志\n案例管理\n案例设置\n标准报表-经济效益\n标准报表-原料采购\n标准报表-产品销售\n标准报表-装置能力\n标准报表-装置详细\n标准报表-混分器\n标准报表-公用工程\n标准报表-物料流向\n标准报表-物料性质\n标准报表-油品调合\n标准报表-物料盈亏平衡\n标准报表-公用工程装置能力\n标准报表-流量约束',
     '功能', '高', '原始', '', '刘海晴', None, '', ''),
    ('SR-TPT-00023', 'IR-TPT-00019，IR-TPT-00001', '计划调度优化Agents', '计划调度优化', '自动测算、模型校核、结果分析融合',
     '通过Agent实现CASE的自动创建、约束修改和求解运行。\n获取企业全厂物料性质数据、装置物料平衡数据、装置的DB数据、装置公用工程（水、电、汽、风）数据和三剂辅材等数据，利用数据驱动模型校核装置产品分布、公用工程消耗和运行成本数据；大模型采用装置生产运行数据微调装置模型，辅助校核计划优化模型。\n自动萃取“计划平台”输出的多个测算方案结果，并融合“垂域知识库”的领域知识，进行多维度的对比分析和根因洞察。最终，模块将自动生成包含关键异同点、效益瓶颈分析的可视化报告和决策建议',
     '功能', '高', '原始', '', '刘海晴', None, '', ''),
    ('SR-TPT-00024', 'IR-TPT-00019，IR-TPT-00001', '计划调度优化Agents', '统一平台', '统一平台技术路线需求',
     '容器化(根据Agent业务划分，重新规划微服务结构)，K8S统一管理(提供安全性/稳定性要求的统一标准)\n银河麒麟系统适配\n数据支持达梦数据库\n账户/权限体系\n中间件(pg、lotdb、redis、nginx)\nU界面风格适配',
     '功能', '高', '原始', '', '刘海晴', None, '', ''),
    ('SR-TPT-00025', 'IR-TPT-00020', '公用工程优化Agents', 'CMS-碳盘查', '碳盘查融合需求',
     '多组织节点改造',
     '功能', '高', '原始', '', '朱倩', None, '', ''),
    ('SR-TPT-00026', 'IR-TPT-00020', '公用工程优化Agents', '无人调度', '无人调度融合需求',
     '无人调度适配TPT平台，能在TPT 后台管理中配置与我的应用中调度大屏挂载；',
     '功能', '高', '原始', '', '刘佳', None, '', ''),
    ('SR-TPT-00027', 'IR-TPT-00021', '换热网络评估优化Agents', '换热网络评估Agent', '换热网络评估Agent需求',
     '创建评估agent，评估对象中新增“换热网络”\n配置换热器信息、流股信息、公用工程信息、参数位号信息，并进行校验（校验失败需支持在线修改），完成模型基础信息配置\n配置相关评估参数，进行换热器与换热网络评估，输出评估概述、评估报告、换热网络结构图。其中，报告与图均支持预览与下载\n1、支持在线绑定/导入位号，关联工厂实时数据；\n2、设置运行频率\n1、展示系统当前能耗水平与节能潜力；\n2、展示换热网络评估结果：不合理换热器信息、夹点温度等关键参数\n3、展示换热器评估结果：换热器数量、高能耗/超负荷/低效率换热器、换热器评估信息\n4、展示换热网络结构图，并与大屏风格保持一致\n5、支持查看历史记录，并保存每次计算的换热器评估报告与换热网络评估报告，支持下载\n6、支持查看各换热器性能历史趋势\n7、支持查看各类公共工程耗量历史趋势',
     '功能', '高', '原始', '', '刘佳', None, '', ''),
    ('SR-TPT-00028', 'IR-TPT-00021', '换热网络评估优化Agents', '换热网络优化Agent', '换热网络优化Agent需求',
     '创建评估agent，优化对象中新增“换热网络”，支持导入已建立的评估agent的数据信息\n配置换热器信息、流股信息、公用工程信息、参数位号信息，并进行校验（校验失败需支持在线修改），完成模型基础信息配置\n配置换热器/换热网络改造相关参数，展示改造结果，包括改造方案总结、方案对比、换热网络/换热器改造报告、换热网络结构图。其中，报告与图均支持预览与下载\n用于自动存储最近50份改造记录、报告，报告支持下载\n1、对于SAAS版（用户试用）：不支持下载图和报告，且表格和报告的预览需要有一定的限制；\n2、对于边缘版部署用户无此限制',
     '功能', '高', '原始', '', '刘佳', None, '', ''),
    ('SR-TPT-00029', 'IR-TPT-00022，IR-TPT-00001', '智能仿真Agents', '国产化', '国产化改造',
     '模型组态软件国产化&Web化，支持国产麒麟操作系统\n评分组态软件国产化&Web化，支持国产麒麟操作系统\n高级故障组态软件国产化&Web化，支持国产麒麟操作系统',
     '功能', '高', '原始', '', '张莹', None, '', ''),
    ('SR-TPT-00030', 'IR-TPT-00022，IR-TPT-00001', '智能仿真Agents', 'AI操作培训专家', '操作培训专家融合',
     '原运行期软件，包含OTS服务器、评分引擎等，支持容器化部署\n采用postgresql作为底层数据库，并支持统一部署\n原学员站软件相关功能，集成到Web平台上，支持网页访问\n原教师站软件相关功能，集成到Web平台上，支持网页访问\n支持将所有存档部署在同一个文件服务容器中，通过学员账号进行访问\n集成AI相关功能，实时解答培训疑问、AI纠正操作错误，自动记录学习数据，生成个性化培训方案与技能评估报告等',
     '功能', '高', '原始', '', '张莹', None, '', ''),
    ('SR-TPT-00031', 'IR-TPT-00022，IR-TPT-00001', '智能仿真Agents', 'AI理论考试专家', '理论考试专家融合',
     '支持根据用户上传文档，自动提取文档内容，并生成试题库\n支持通过试题库自动生成试卷，针对学员学习情况定制化生成\n针对学员考试答题情况，AI阅卷评分，并生成考试报告\n支持对用户上传的文档进行AI智能学习，进行知识点的提取和归纳',
     '功能', '高', '原始', '', '张莹', None, '', ''),
    ('SR-TPT-00032', 'IR-TPT-00022，IR-TPT-00001', '智能仿真Agents', '机理+AI混合模型', '模型训练、混合模型生成需求',
     '支持用户上传数据或者接入数据配置之后进行混合模型训练，生成数据模型\n支持将训练的数据模型与基础机理模型结合，形成混合模型，进行动态模拟\n支持调用混合模型进行动态仿真，开展培训、预测等其他应用',
     '功能', '高', '原始', '', '张莹', None, '', ''),
    ('SR-TPT-00033', 'IR-TPT-00022，IR-TPT-00001', '智能仿真Agents', '自动组态Agent', '工艺、规程、故障自动化组态需求',
     '支持根据PID图或者对话等，进行工艺组态或者修改，进而将工艺组态过程自动化\n支持根据用户提供的操作规程等，自动进行评分过程组态或者修改组态\n支持根据用户提供的故障手册等，自动进行故障组态或者修改组态',
     '功能', '高', '原始', '', '张莹', None, '', ''),
    ('SR-TPT-00034', 'IR-TPT-00022，IR-TPT-00001', '智能仿真Agents', '仿真模拟应用', '仿真应用扩大需求',
     '1.基于规程自动化仿真模拟操作，过程可以识别规程的合理性或者模型的正确性，并给出影响后果；仿真操作每个步骤可以识别计算出能耗物耗节能等数据.\n2.基于其他验证类场景，匹配工况进行模拟结果输出\n3.基于加速模拟出预测数据\n4.基于仿真模型对比实时数据做偏差分析',
     '功能', '高', '原始', '', '张莹', None, '', ''),
    ('SR-TPT-00035', 'IR-TPT-00022，IR-TPT-00001', '智能仿真Agents', '故障模拟专家', '故障模块应用需求',
     '1.模拟组分异常、泄露、管道冻住、火炬气等装置常见故障，并能指导用户如果解决，考虑用Direct解决\n2.重新的设计故障模块，形成专题的故障或者异常工况的培训和模拟\n3.匹配LLM的知识库统一设计\n4.基于故障库分析和验证故障处置方案的合理性和优化方案（故障模拟+分析，需要结合AI）\n5.基于数据和机理生成高保真的故障工况',
     '功能', '高', '原始', '', '张莹', None, '', ''),
    ('SR-TPT-00036', 'IR-TPT-00022，IR-TPT-00001', '智能仿真Agents', '课件制作应用', '内置模型制作对应的课件，开展线上培训内容',
     '对于每个内置的模型，需要开发相应的实操培训课件，做云化的OTS培训业务',
     '功能', '高', '原始', '', '张莹', None, '', ''),
    ('SR-TPT-00037', 'IR-TPT-00023', '非功能性需求', '性能需求', '轻量化部署需求',
     '支持云企边部署：支持边缘端部署轻量化32C64G；中间化轻量化；',
     '性能', '高', '原始', '', '刘义淑', None, '', ''),
    ('SR-TPT-00038', 'IR-TPT-00024', '非功能性需求', '安全性需求', '等保与AI数据安全需求',
     '系统常规等级保护2级安全性，AI公平、伦理、私密性安全',
     '安全性', '高', '原始', '', '余泽超', None, '', ''),
    ('SR-TPT-00039', 'IR-TPT-00025', '非功能性需求', '可服务性需求', '工程实施效率提升需求',
     '支持自动化工具：建模&实施自动化、一键安装包',
     '可服务性', '高', '原始', '', '刘义淑', None, '', ''),
    ('SR-TPT-00040', 'IR-TPT-00026', '非功能性需求', '易用性需求', '易用性提升需求',
     '主要通过CUI进行显示和生成，部分可以利用GUI固化的页面展示',
     '易用性', '高', '原始', '', '叶学莉', None, '', ''),
    ('SR-TPT-00041', 'IR-TPT-00027', '非功能性需求', '兼容性需求', 'agents兼容与国产化支持需求',
     '云企边模型、算法、组态、agents 升级后支持相互兼容； 支持国产化中间件适配，含人大金仓等。',
     '兼容性', '高', '原始', '', '张莹', None, '', ''),
]


def find_db() -> Path:
    env = os.environ.get("DATABASE_URL", "")
    if env.startswith("sqlite:///"):
        p = Path(env.replace("sqlite:///", "").lstrip("/"))
        if p.exists():
            return p
    for c in CANDIDATES:
        p = Path(c)
        if p.exists():
            return p
    for name in ("database_prod.sqlite", "database.sqlite"):
        p = Path(name)
        if p.exists():
            return p
    sys.exit("!! 找不到数据库（database_prod.sqlite / database.sqlite），请在 backend 目录运行")


def ensure_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tm_tasks)")}
    for name, decl in NEW_COLS:
        if name in cols:
            continue
        conn.execute(f"ALTER TABLE tm_tasks ADD COLUMN {name} {decl}")
        print(f"  + 加列 tm_tasks.{name}")


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def backup_db(db: Path) -> None:
    bak = db.with_suffix(".sqlite.bak_seed_standalone")
    if bak.exists():
        return
    shutil.copy2(db, bak)
    print(f"  + 备份 → {bak.name}")


def main() -> None:
    db = find_db()
    print(f"== 导入 {PROJECT_NAME}（单文件零依赖版，{len(SRS)} 条SR） ==")
    print(f"  数据库: {db}")
    backup_db(db)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        ensure_columns(conn)

        lead = conn.execute(
            "SELECT id, real_name FROM users WHERE username=?", (LEAD_USERNAME,)
        ).fetchone()
        if not lead:
            sys.exit(f"!! 用户 {LEAD_USERNAME} 不存在")
        admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        if not admin:
            sys.exit("!! admin 用户不存在")
        print(f"  负责人: {lead['real_name']} (@{LEAD_USERNAME})")

        all_users = conn.execute("SELECT id, real_name FROM users").fetchall()
        name2id = {u["real_name"].strip(): u["id"] for u in all_users if u["real_name"]}
        matched = sum(1 for r in SRS if r[10] and r[10] in name2id)
        unmatched = sorted({r[10] for r in SRS if r[10] and r[10] not in name2id})
        print(f"  验证人匹配: {matched}/{len(SRS)}，未匹配: {unmatched if unmatched else '无'}")

        proj = conn.execute(
            "SELECT id FROM tm_projects WHERE name=?", (PROJECT_NAME,)
        ).fetchone()
        if proj:
            pid = proj["id"]
            print("  ~ 项目已存在，清空旧数据")
            tids = [r[0] for r in conn.execute(
                "SELECT id FROM tm_tasks WHERE project_id=?", (pid,)
            )]
            aids = [r[0] for r in conn.execute(
                "SELECT id FROM tm_actions WHERE project_id=?", (pid,)
            )]
            if aids:
                conn.executemany(
                    "DELETE FROM tm_daily_updates WHERE action_id=?",
                    [(a,) for a in aids])
                conn.executemany(
                    "DELETE FROM tm_action_corrections WHERE action_id=?",
                    [(a,) for a in aids])
                conn.executemany(
                    "UPDATE tm_actions SET source_action_id=NULL WHERE source_action_id=?",
                    [(a,) for a in aids])
                conn.executemany(
                    "DELETE FROM tm_actions WHERE id=?", [(a,) for a in aids])
            if tids:
                conn.executemany(
                    "DELETE FROM tm_task_week_progress WHERE task_id=?",
                    [(t,) for t in tids])
                conn.executemany(
                    "DELETE FROM tm_task_stage_snapshots WHERE task_id=?",
                    [(t,) for t in tids])
                conn.executemany(
                    "DELETE FROM tm_task_update_logs WHERE task_id=?",
                    [(t,) for t in tids])
                conn.executemany(
                    "DELETE FROM tm_task_testers WHERE task_id=?",
                    [(t,) for t in tids])
                conn.executemany(
                    "DELETE FROM tm_tasks WHERE id=?", [(t,) for t in tids])
            conn.execute("DELETE FROM tm_domains WHERE project_id=?", (pid,))
            conn.execute("DELETE FROM tm_push_snapshots")
            conn.execute("DELETE FROM tm_push_runs")
        else:
            pid = new_id()
            conn.execute(
                "INSERT INTO tm_projects "
                "(id, name, description, status, created_by, created_at, updated_at) "
                "VALUES (?, ?, ?, 'active', ?, ?, ?)",
                (pid, PROJECT_NAME, PROJECT_DESC, admin["id"], now_iso(), now_iso()),
            )
            print("  + 创建项目")

        domains_order = []
        for r in SRS:
            if r[2] not in domains_order:
                domains_order.append(r[2])
        cat_count = {c: sum(1 for r in SRS if r[2] == c) for c in domains_order}
        domains_sorted = sorted(domains_order, key=lambda c: -cat_count[c])
        domain_ids: dict[str, str] = {}
        for i, c in enumerate(domains_sorted):
            did = new_id()
            conn.execute(
                "INSERT INTO tm_domains "
                "(id, project_id, name, sort_order, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (did, pid, c, i + 1, now_iso()),
            )
            domain_ids[c] = did
        print(f"  + 创建 {len(domain_ids)} 个域")

        n = 0
        for r in SRS:
            sr, ir, dom, mod, title, req, rt, prio, cf, ac, vn, va, vr, rk = r
            verifier_id = name2id.get(vn) if vn else None
            remark = rk or ""
            if vn and not verifier_id:
                note = f"验证人：{vn}"
                remark = f"{remark}\n{note}".strip() if remark else note
            tid = new_id()
            conn.execute(
                "INSERT INTO tm_tasks ("
                "id, project_id, domain_id, title, requirement, "
                "sr_code, ir_codes, module, req_type, priority, change_flag, "
                "acceptance_criteria, verifier_id, verified_at, verify_result, remark, "
                "subtasks, lead_id, status, req_stage, "
                "created_by, published_at, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, 'published', 'developing', ?, ?, ?, ?)",
                (tid, pid, domain_ids[dom], title, req,
                 sr, ir, mod, rt, prio, cf,
                 ac, verifier_id, va, vr, remark,
                 lead["id"], admin["id"], now_iso(), now_iso(), now_iso()),
            )
            conn.execute(
                "INSERT INTO tm_task_update_logs "
                "(id, task_id, user_id, summary, detail, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (new_id(), tid, admin["id"], "导入：TPT v2.3 产品包需求（Excel全量/单文件零依赖版）",
                 f"seed_tpt_v23_standalone | {sr}", now_iso()),
            )
            n += 1

        conn.commit()
        print(f"\n  ✓ 导入完成：{n} 个Task，{len(domain_ids)} 个域")
        print(f"  项目：{PROJECT_NAME}｜负责人：{lead['real_name']} (@{LEAD_USERNAME})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
