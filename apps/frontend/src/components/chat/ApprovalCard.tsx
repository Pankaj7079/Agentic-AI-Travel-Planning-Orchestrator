import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

interface Approval {
  approval_id: string
  trip_id: string
  status: string
  type: string
  message: string
  context: any
}

interface ApprovalCardProps {
  approval: Approval
  onApprove: () => void
  onReject: () => void
}

export function ApprovalCard({ approval, onApprove, onReject }: ApprovalCardProps) {
  return (
    <Card className="w-full max-w-md mx-auto my-4 border-l-4 border-l-yellow-500 bg-yellow-500/5">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <span>Action Required</span>
        </CardTitle>
        <CardDescription>The agent needs your input to proceed.</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm font-medium mb-2">{approval.message}</p>
        {approval.context && Object.keys(approval.context).length > 0 && (
          <div className="bg-background/50 p-3 rounded-md text-xs font-mono overflow-x-auto">
            {JSON.stringify(approval.context, null, 2)}
          </div>
        )}
      </CardContent>
      <CardFooter className="flex justify-end gap-3">
        <Button variant="outline" onClick={onReject}>Reject</Button>
        <Button onClick={onApprove}>Approve</Button>
      </CardFooter>
    </Card>
  )
}
