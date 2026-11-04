import { CheckCircleOutlined, DisconnectOutlined, SyncOutlined } from '@ant-design/icons'
import { Tag } from 'antd'
import { useHealth } from '../api/hooks'
import { vi } from '../lib/vi'

/** Trạng thái API ở header. Lỗi dùng màu cam (đỏ chỉ dành cho "Nguy hiểm"). */
export function ApiStatus() {
  const { data, isPending, isError } = useHealth()
  if (isPending) {
    return (
      <Tag icon={<SyncOutlined spin />} color="processing">
        {vi.api.checking}
      </Tag>
    )
  }
  if (isError) {
    return (
      <Tag icon={<DisconnectOutlined />} color="warning">
        {vi.api.down}
      </Tag>
    )
  }
  return (
    <Tag icon={<CheckCircleOutlined />} color="success">
      {vi.api.ok(data.gpu_core)}
    </Tag>
  )
}
