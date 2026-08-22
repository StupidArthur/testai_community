/**
 * 项目管理使用说明（页内抽屉）：简略版上手；完整版可下载。
 */
import { Button, Drawer } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import './tmSheet.css'

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
            <h3 className="tm-sheet__h">模块能做什么</h3>
            <p className="tm-sheet__body">
              按周管理测试：维护 Task / Action、填日更与阻塞，大屏看进展；钉钉推送日报 / 周报。
            </p>
          </section>

          <section className="tm-sheet__section">
            <h3 className="tm-sheet__h">基本概念</h3>
            <p className="tm-sheet__body">
              <strong>项目 / 领域</strong>：分类。
              <br />
              <strong>Task</strong>：一项测试工作（可跨周）；lead = 测试负责人。
              <br />
              <strong>Action</strong>：本周具体事项；owner = 本周负责人（写日更）。
              <br />
              <strong>周界</strong>：默认周三 17:00 切周（测试管理员可改）。
            </p>
          </section>

          <section className="tm-sheet__section">
            <h3 className="tm-sheet__h">按角色做什么</h3>
            <p className="tm-sheet__body">
              <strong>Action owner</strong>
              <br />
              · 「我的 Action」写日更（进度 % + 说明；有阻塞再填）
              <br />
              · 建议 19:50 前写完；之后当天锁定
              <br />
              · 做完：日更到 100% → 标记完成
              <br />
              <br />
              <strong>Task lead</strong>
              <br />
              · 切周后新建 / 复制 Action → 发布
              <br />
              · 周结束前手填 Task 周进度；未填用 Action 平均
              <br />
              · 收尾改「已完成」；暂不投入 → 归档
              <br />
              <br />
              <strong>测试管理员</strong>
              <br />
              · 建项目 / 领域 / Task；配钉钉；改周结束时刻
            </p>
          </section>

          <section className="tm-sheet__section">
            <h3 className="tm-sheet__h">什么时候写哪种进度</h3>
            <p className="tm-sheet__body">
              <strong>Action 日更</strong>（每天）：有进展就写；只能升高；下调用更正说明；阻塞留空保存即解除。
              <br />
              <br />
              <strong>Task 周进度</strong>（每周）：周结束前填一次，给周报用。
            </p>
          </section>

          <section className="tm-sheet__section">
            <h3 className="tm-sheet__h">三个页签</h3>
            <p className="tm-sheet__body">
              <strong>本周大屏</strong>：进度与阻塞。
              <br />
              <strong>工作台</strong>：维护 Task / Action。
              <br />
              <strong>我的 Action</strong>：日更入口。
            </p>
          </section>

          <section className="tm-sheet__section">
            <h3 className="tm-sheet__h">其他</h3>
            <p className="tm-sheet__body">
              阻塞看最新日更字段。Action 发布后字段锁定，纠错用更正说明。标记完成须 100%。
            </p>
          </section>
        </div>
      </div>
    </Drawer>
  )
}
