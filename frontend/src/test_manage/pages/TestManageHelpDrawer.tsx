/**
 * 项目管理使用说明（页内抽屉）：简略版上手；完整版可下载。
 */
import { Button, Drawer, Space, Typography } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'

const { Title, Paragraph, Text } = Typography

/** 与 doc/test_manage_product_guide.md 同步的静态下载地址（Vite public） */
const FULL_GUIDE_URL = '/docs/test_manage_product_guide.md'
/** 浏览器另存为时的默认文件名 */
const FULL_GUIDE_DOWNLOAD_NAME = '项目管理-完整使用说明.md'

type Props = {
  open: boolean
  onClose: () => void
}

export default function TestManageHelpDrawer(props: Props) {
  return (
    <Drawer
      title="项目管理 · 使用说明"
      placement="right"
      width={440}
      open={props.open}
      onClose={props.onClose}
      destroyOnClose
    >
      <div data-testid="tm-help-drawer">
        <Space direction="vertical" size={12} style={{ width: '100%', marginBottom: 16 }}>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            以下为简略版。完整分模块说明（概念 / 各页签 / 日更 / 权限 / FAQ）请下载查看。
          </Paragraph>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            href={FULL_GUIDE_URL}
            download={FULL_GUIDE_DOWNLOAD_NAME}
            data-testid="tm-help-download"
            block
          >
            下载完整使用说明
          </Button>
        </Space>

        <Title level={5}>模块能做什么</Title>
        <Paragraph>
          按周管理测试工作：维护 Task / Action、填写当日进度与风险，并在大屏查看进展。系统会向钉钉推送日报与周报。
        </Paragraph>

        <Title level={5}>基本概念</Title>
        <Paragraph>
          <Text strong>项目 / 领域</Text>：工作分类。
          <br />
          <Text strong>Task</Text>：一项测试工作（可跨周持续）。
          <br />
          <Text strong>Action</Text>：本周要执行的具体事项，含负责人、进度与风险。
          <br />
          <Text strong>周界</Text>：默认每周三 <Text strong>17:00</Text> 切周（管理员可改本周结束时刻）。
        </Paragraph>

        <Title level={5}>三个页签</Title>
        <Paragraph>
          <Text strong>本周大屏</Text>：查看整体进度、风险与「需关注」列表；可切历史周（只读）。
          <br />
          <Text strong>工作台</Text>：按「我的 Task / 其他 / 全部」查看。我的 Task = 你是测试负责人的条目。可「新建
          Action」或「复制上周」。
          <br />
          <Text strong>我的 Action</Text>：对指派给自己的 Action 提交当日进度。
        </Paragraph>

        <Title level={5}>提交日更</Title>
        <Paragraph>
          在「我的 Action」中打开对应条目，填写进度百分比与说明。
          有阻塞时填写风险；无阻塞时风险栏留空。
          当日日更在 <Text strong>19:50</Text> 后锁定；钉钉日报约 <Text strong>20:00</Text> 发送一条。
        </Paragraph>

        <Title level={5}>风险如何判定</Title>
        <Paragraph>
          以该 Action <Text strong>最新一条日更</Text> 中的风险字段为准。
          风险栏有内容 → 计入开放风险；留空保存 → 视为已解除。
          复制到下一周的 Action 不会带入上周风险，需在新一周日更中重新填写。
        </Paragraph>

        <Title level={5}>发布与修改</Title>
        <Paragraph>
          Action 发布后，标题、负责人、测试内容、环境等字段锁定，不可直接改派。
          需要更正时使用「更正说明」；需要更换负责人时，新建一条 Action 并指定新负责人。
          标记完成前，日更进度须达到 100%。Action 不支持取消。
        </Paragraph>

        <Title level={5}>Task 状态</Title>
        <Paragraph>
          Task 跨周持续，不按周新建。状态仅两种：
          <Text strong>进行中</Text>（可添加本周 Action）与
          <Text strong>已完成</Text>（不可再添加 Action）。
          不会因下属 Action 全部完成而自动变更，需手动修改。
        </Paragraph>

        <Title level={5}>需关注</Title>
        <Paragraph>
          包含：存在开放风险，或仍有进行中的 Action。仅含草稿、无进行中事项的 Task 不计入。
        </Paragraph>

        <Paragraph type="secondary" style={{ marginTop: 16 }}>
          仍有疑问时，请下载完整说明按模块查阅（工作台 / 大屏 / 日更 / 复制 / FAQ 等）。
        </Paragraph>
      </div>
    </Drawer>
  )
}
