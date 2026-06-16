/**
 * 平台集成工具页顶栏：返回工具集首页。
 */
import { Button } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

export default function ReturnToToolHubButton() {
  const navigate = useNavigate()

  return (
    <Button
      type="link"
      icon={<ArrowLeftOutlined />}
      onClick={() => navigate('/tool-hub')}
      style={{ paddingLeft: 0, marginBottom: 8 }}
    >
      返回工具集
    </Button>
  )
}
