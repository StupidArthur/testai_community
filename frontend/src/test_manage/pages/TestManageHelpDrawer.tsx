/**
 * 项目管理使用说明（页内抽屉）：傻瓜式简略版；完整版可下载。
 */
import { Button, Drawer } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import './tmSheet.css'

/** 与 docs/test_manage_product_guide.md 同步的静态下载地址（Vite public） */
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
      styles={{ body: { paddingTop: 12, paddingBottom: 24 } }}
    >
      <div className="tm-sheet" data-testid="tm-help-drawer">
        <div className="tm-sheet__stack">
          <section className="tm-sheet__section">
            <p className="tm-sheet__body">简略版。完整说明请下载。</p>
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
          </section>

          <section className="tm-sheet__section">
            <h3 className="tm-sheet__h">一句话：这个模块干什么</h3>
            <p className="tm-sheet__body">
              按周记录测试工作（Task → Action → 每天日更），自动汇总到大屏，钉钉每天 / 每周自动推送。
            </p>
          </section>

          <section className="tm-sheet__section">
            <h3 className="tm-sheet__h">记住三个时间点</h3>
            <p className="tm-sheet__body">
              <strong>每天 19:50</strong>：写完当天日更（之后当天日更锁定，日报约 20:00 发）
              <br />
              <strong>每周三 16:55</strong>：本周内容最后保存机会（之后锁定，改不了了）
              <br />
              <strong>每周三 17:00</strong>：切新周，开始建下周 Action（周报约 17:15 发）
            </p>
          </section>

          <section className="tm-sheet__section">
            <h3 className="tm-sheet__h">我是普通测试（Action 负责人）</h3>
            <p className="tm-sheet__body">
              每天 3 步：
              <br />
              1. 点「<strong>我的 Action</strong>」页签
              <br />
              2. 点自己那条 → 填<strong>进度 %</strong> + <strong>进度说明</strong>（有阻塞勾「是否阻塞」）
              <br />
              3. 保存。做完了 → 进度填 <strong>100%</strong> → 点「标记完成」
              <br />
              <br />
              填错了想改？进度只能往上涨；写错的说明用「更正说明」补一条。
            </p>
          </section>

          <section className="tm-sheet__section">
            <h3 className="tm-sheet__h">我是 Task 负责人（lead）</h3>
            <p className="tm-sheet__body">
              每周三切周后 3 步：
              <br />
              1. 点「<strong>工作台</strong>」→ 找到自己的 Task
              <br />
              2. 点「<strong>+ Action</strong>」新建，或点「操作 → 详情」里<strong>复制上周</strong>（改标题 / 负责人后发布）
              <br />
              3. <strong>周三 16:55 前</strong>填「操作 → 进度」里的本周 Task 进度
              <br />
              <br />
              主题做完 → Task 改「已完成」；暂时不做了 → 归档。
            </p>
          </section>

          <section className="tm-sheet__section">
            <h3 className="tm-sheet__h">我是测试管理员</h3>
            <p className="tm-sheet__body">
              1. 「工作台 → 新建」下拉：建<strong>项目 / 领域 / Task</strong>
              <br />
              2. 配好钉钉推送（每天 20:00 日报、周三 17:15 周报自动发）
              <br />
              3. 抽查大屏「需关注」；周结束固定周三 17:00，<strong>不用设时间</strong>
            </p>
          </section>

          <section className="tm-sheet__section">
            <h3 className="tm-sheet__h">三个页签去哪看</h3>
            <p className="tm-sheet__body">
              <strong>大屏</strong>：给领导看进度 / 阻塞（今日 / 本周 / 历史）
              <br />
              <strong>工作台</strong>：建 Task / Action、填周进度
              <br />
              <strong>我的 Action</strong>：每天写日更新的入口
            </p>
          </section>

          <section className="tm-sheet__section">
            <h3 className="tm-sheet__h">最常卡壳的 4 件事</h3>
            <p className="tm-sheet__body">
              · Action 发布后改不了 → 用「更正说明」补，或新建一条
              <br />
              · 点不了「完成」→ 先把日更进度写到 <strong>100%</strong>
              <br />
              · 风险没了 → 当天日更把风险栏<strong>留空</strong>保存
              <br />
              · 周三 16:55 后什么都改不了 → 等切周，或下周补更正说明
            </p>
          </section>
        </div>
      </div>
    </Drawer>
  )
}
