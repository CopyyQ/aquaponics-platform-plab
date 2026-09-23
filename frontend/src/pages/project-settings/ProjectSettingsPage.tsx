import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Globe2 } from "lucide-react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { projectNotificationApi } from "@/entities/project-notification/api/project-notification-api";
import type { PublicSettings } from "@/entities/project-notification/model/types";
import { useProtectedQueryScope } from "@/features/auth/model/use-protected-query-scope";
import { formatBackendError } from "@/shared/api/backend-error";
import { Button } from "@/shared/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/shared/ui/card";
import { EmptyState } from "@/shared/ui/empty-state";
import { Label } from "@/shared/ui/label";
import { Skeleton } from "@/shared/ui/skeleton";
import { Switch } from "@/shared/ui/switch";

export function ProjectSettingsPage() {
  const projectId = Number(useParams().projectId);
  const { active, queryScope } = useProtectedQueryScope();
  const client = useQueryClient();
  const queryKey = [
    "project-public-settings",
    ...queryScope,
    projectId,
  ] as const;
  const settings = useQuery({
    queryKey,
    queryFn: () => projectNotificationApi.getPublicSettings(projectId),
    enabled: active && Number.isFinite(projectId),
  });
  if (settings.isLoading) return <Skeleton className="h-80" />;
  if (!settings.data)
    return (
      <EmptyState
        icon={Globe2}
        title="Không thể tải cài đặt công khai"
        description="Vui lòng kiểm tra quyền quản lý dự án."
      />
    );
  return (
    <PublicSettingsForm
      key={`${settings.data.enabled}`}
      projectId={projectId}
      initial={settings.data}
      onSaved={(value) => client.setQueryData(queryKey, value)}
    />
  );
}

function PublicSettingsForm({
  projectId,
  initial,
  onSaved,
}: {
  projectId: number;
  initial: PublicSettings;
  onSaved: (value: typeof initial) => void;
}) {
  const [enabled, setEnabled] = useState(initial.enabled);
  const mutation = useMutation({
    mutationFn: () =>
      projectNotificationApi.updatePublicSettings(projectId, {
        enabled,
      }),
    onSuccess: (value) => {
      onSaved(value);
      toast.success("Đã lưu cài đặt theo dõi công khai");
    },
    onError: (error) =>
      toast.error(formatBackendError(error, "Không thể lưu cài đặt công khai")),
  });
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-bold">Cài đặt dự án</h2>
        <p className="text-sm text-muted-foreground">
          Quản lý trạng thái cho phép đọc dữ liệu công khai của dự án qua hạ tầng hiện tại.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Theo dõi công khai</CardTitle>
          <CardDescription>
            Cho phép dữ liệu giám sát công khai ở chế độ chỉ đọc, không tạo gateway hoặc tunnel riêng.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="public-enabled">Bật theo dõi công khai</Label>
            <Switch
              id="public-enabled"
              checked={enabled}
              onCheckedChange={setEnabled}
              disabled={!initial.remote_monitoring_available}
              aria-describedby="remote-monitoring-scope"
            />
          </div>
          <div id="remote-monitoring-scope" className="grid gap-3 rounded-md border p-4 text-sm sm:grid-cols-2">
            <div><p className="font-medium">Phạm vi chia sẻ</p><p className="text-muted-foreground">Giám sát dự án</p></div>
            <div><p className="font-medium">Quyền truy cập</p><p className="text-muted-foreground">Chỉ đọc</p></div>
            <div><p className="font-medium">Có thể xem</p><p className="text-muted-foreground">Thiết bị, cảm biến, năng lượng, biểu đồ và cảnh báo</p></div>
            <div><p className="font-medium">Không thể</p><p className="text-muted-foreground">Điều khiển, cấu hình, MQTT, thành viên hoặc Telegram</p></div>
          </div>
        </CardContent>
        <CardFooter>
          <Button
            disabled={!initial.remote_monitoring_available || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Đang lưu…" : "Lưu cài đặt"}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
