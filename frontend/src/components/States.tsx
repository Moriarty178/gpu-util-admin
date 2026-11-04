import { Alert, Button, Card, Empty, Skeleton } from 'antd'
import { Link } from 'react-router'
import { errorMessage } from '../api/client'
import { useAuth } from '../auth/session'
import { vi } from '../lib/vi'

export function Loading({ rows = 6 }: { rows?: number }) {
  return (
    <Card>
      <Skeleton active paragraph={{ rows }} />
    </Card>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <Alert
      type="warning"
      showIcon
      message={vi.loadError}
      description={errorMessage(error)}
      action={
        onRetry ? (
          <Button size="small" onClick={onRetry}>
            {vi.retry}
          </Button>
        ) : undefined
      }
    />
  )
}

export function NoData({ description = vi.emptyHint }: { description?: string }) {
  const me = useAuth()
  return (
    <Card>
      <Empty description={me.role === 'admin' ? `${vi.empty} — ${description}` : vi.empty}>
        {me.role === 'admin' && (
          <Link to="/imports">
            <Button type="primary">{vi.goImport}</Button>
          </Link>
        )}
      </Empty>
    </Card>
  )
}

export function LimitationNote() {
  return <Alert type="info" showIcon message={vi.limitation} />
}
