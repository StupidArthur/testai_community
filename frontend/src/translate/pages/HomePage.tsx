import { useState } from 'react'
import { Button, Modal, Form, Input, Upload, message } from 'antd'
import { UploadOutlined, DownloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { listJobs, createJob, getPromptsDownloadUrl } from '../../shared/api/translate-jobs'
import { JobList } from '../components/JobList'

export default function HomePage() {
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [uploadForm] = Form.useForm()
  const [fileList, setFileList] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)

  const { data: jobs = [], isLoading, refetch } = useQuery({
    queryKey: ['jobs'],
    queryFn: listJobs,
    refetchInterval: (query) => {
      const hasActive = query.state.data?.some(
        (j) => j.status === 'queued' || j.status === 'running'
      )
      return hasActive ? 2000 : 10000
    },
  })

  const handleUpload = async () => {
    if (!fileList) {
      message.error('请选择 ZIP 文件')
      return
    }
    const name = uploadForm.getFieldValue('name')?.trim() || ''
    setUploading(true)
    try {
      const res = await createJob(fileList, name || undefined)
      message.success('上传成功，任务已加入队列')
      setUploadModalOpen(false)
      uploadForm.resetFields()
      setFileList(null)
      refetch()
    } catch (err: any) {
      message.error(err.message || '上传失败')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8, gap: 8 }}>
        <Button
          icon={<DownloadOutlined />}
          onClick={async () => {
            try {
              const url = await getPromptsDownloadUrl()
              window.open(url, '_blank')
            } catch (err: unknown) {
              message.error(err instanceof Error ? err.message : '下载失败')
            }
          }}
        >
          下载 Prompts
        </Button>
        <Button
          type="primary"
          icon={<UploadOutlined />}
          onClick={() => setUploadModalOpen(true)}
        >
          上传录制文件
        </Button>
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        <JobList jobs={jobs} isLoading={isLoading} refetch={refetch} />
      </div>

      <Modal
        title="上传录制文件"
        open={uploadModalOpen}
        onCancel={() => {
          setUploadModalOpen(false)
          uploadForm.resetFields()
          setFileList(null)
        }}
        onOk={handleUpload}
        okText="开始翻译"
        confirmLoading={uploading}
        destroyOnClose
      >
        <Form form={uploadForm} layout="vertical">
          <Form.Item name="name" label="任务名称">
            <Input placeholder="可选，不填则自动生成" />
          </Form.Item>
          <Form.Item label="录制文件" required>
            <Upload
              accept=".zip"
              maxCount={1}
              fileList={fileList ? [{
                uid: '-1',
                name: fileList.name,
                status: 'done',
              }] : []}
              beforeUpload={(file) => {
                setFileList(file)
                return false
              }}
              onRemove={() => {
                setFileList(null)
              }}
            >
              <Button icon={<UploadOutlined />}>选择 ZIP 文件</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
