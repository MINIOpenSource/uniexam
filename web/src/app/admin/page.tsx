"use client";

import React from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { useExamWebSocket } from '@/hooks/useExamWebSocket';
import { AdminHomeView } from '@/components/admin_views/AdminHomeView';
import type { AdminSectionId } from '@/components/admin_views/AdminSidebar';

export default function AdminPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [paperUpdateVersion, setPaperUpdateVersion] = React.useState(0);

  const {
    status: wsStatus,
    deviceId: currentDeviceId,
    adminLiveConnections,
    adminLiveEvents,
    requestAdminLiveState,
    adminKickDevice,
    clearAdminLiveEvents,
  } = useExamWebSocket({
    token: user?.token || null,
    telemetryContext: {
      pageMode: 'admin_panel',
      examState: 'idle',
    },
    onAdminPaperUpdated: () => {
      setPaperUpdateVersion((v) => v + 1);
    },
  });

  const handleNavigate = (section: AdminSectionId) => {
    switch (section) {
      case 'papers':
        router.push('/admin/papers');
        break;
      case 'questionBanks':
        router.push('/admin/question-banks');
        break;
      case 'settings':
        router.push('/admin/settings');
        break;
      default:
        break;
    }
  };

  return (
    <AdminHomeView
      user={user}
      onNavigate={handleNavigate}
      wsStatus={wsStatus}
      currentDeviceId={currentDeviceId}
      liveConnections={adminLiveConnections}
      liveEvents={adminLiveEvents}
      onRequestRefreshLive={requestAdminLiveState}
      onKickDevice={adminKickDevice}
      onClearEvents={clearAdminLiveEvents}
      paperUpdateVersion={paperUpdateVersion}
    />
  );
}
