import { Button, Result } from 'antd'
import { Link } from 'react-router'
import { vi } from '../lib/vi'

export default function NotFound() {
  return (
    <Result
      status="404"
      title={vi.notFound.title}
      extra={
        <Link to="/">
          <Button type="primary">{vi.notFound.back}</Button>
        </Link>
      }
    />
  )
}
