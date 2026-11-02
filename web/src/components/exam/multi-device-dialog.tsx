"use client";

import type { ConnectedDevice, WsConnectionStatus } from '@/types/exam';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/hooks/useTranslation';

interface MultiDeviceDialogProps {
  isOpen: boolean;
  onClose: () => void;
  wsStatus: WsConnectionStatus;
  currentDeviceId: string;
  devices: ConnectedDevice[];
  onKickDevice: (targetDeviceId: string) => void;
  onJumpToDevicePaper?: (paperId: string, questionIndex: number) => void;
}

export function MultiDeviceDialog({
  isOpen,
  onClose,
  wsStatus,
  currentDeviceId,
  devices,
  onKickDevice,
  onJumpToDevicePaper,
}: MultiDeviceDialogProps) {
  const { t } = useTranslation();

  if (!isOpen) return null;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg p-5">
        <DialogHeader className="border-b pb-3">
          <DialogTitle className="text-base font-semibold">
            {t('multiDevice.title')}
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            {t('multiDevice.description')}
          </DialogDescription>
        </DialogHeader>

        <div className="my-3 space-y-2.5">
          <div className="flex items-center justify-between rounded border bg-muted/40 px-3 py-2 text-xs">
            <span className="text-muted-foreground">{t('multiDevice.wsStatusLabel')}</span>
            <span className="font-medium">
              {wsStatus === 'connected'
                ? t('multiDevice.statusConnected')
                : wsStatus === 'connecting'
                ? t('multiDevice.statusConnecting')
                : t('multiDevice.statusDisconnected')}
            </span>
          </div>

          <div className="space-y-2 max-h-64 overflow-y-auto">
            {devices.length === 0 ? (
              <div className="py-6 text-center text-xs text-muted-foreground">
                {t('multiDevice.noDevices')}
              </div>
            ) : (
              devices.map((dev) => {
                const isSelf = dev.device_id === currentDeviceId;
                return (
                  <div
                    key={dev.device_id}
                    className="flex flex-col gap-2 rounded border bg-background p-3 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-foreground">{dev.device_name}</span>
                        {isSelf && (
                          <span className="rounded border border-primary/40 bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">
                            {t('multiDevice.currentDevice')}
                          </span>
                        )}
                      </div>
                      <span className="font-mono text-[11px] text-muted-foreground">
                        IP: {dev.ip_address}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-muted-foreground">
                      <span>
                        {t('multiDevice.statusLabel')}{' '}
                        {dev.active_paper_id
                          ? t('multiDevice.statusTakingExam', {
                              paperId: dev.active_paper_id.slice(0, 8),
                              questionIndex: (dev.current_question_index || 0) + 1,
                            })
                          : t('multiDevice.statusIdle')}
                      </span>

                      <div className="flex items-center gap-1.5">
                        {!isSelf && dev.active_paper_id && onJumpToDevicePaper && (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-6 px-2 text-[11px]"
                            onClick={() => {
                              onJumpToDevicePaper(
                                dev.active_paper_id!,
                                dev.current_question_index || 0
                              );
                              onClose();
                            }}
                          >
                            {t('multiDevice.jumpToPaper')}
                          </Button>
                        )}
                        {!isSelf && (
                          <Button
                            type="button"
                            variant="destructive"
                            size="sm"
                            className="h-6 px-2 text-[11px]"
                            onClick={() => onKickDevice(dev.device_id)}
                          >
                            {t('multiDevice.kickDevice')}
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <DialogFooter className="border-t pt-3">
          <Button variant="outline" size="sm" onClick={onClose}>
            {t('multiDevice.close')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
