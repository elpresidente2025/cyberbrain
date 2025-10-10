// src/pages/PostDetailPage.jsx
import React, { useEffect, useState } from "react";
import {
  Box,
  Paper,
  Typography,
  Button,
  CircularProgress,
  Stack,
} from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { useParams, useNavigate } from "react-router-dom";
import { callFunctionWithNaverAuth } from '../services/firebaseService';
import DashboardLayout from "../components/DashboardLayout";
import { functions } from '../services/firebase';
import { NotificationSnackbar, useNotification } from '../components/ui';

const htmlToText = (html) => {
  if (!html) return "";
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  const text = tmp.textContent || tmp.innerText || "";
  return text.replace(/\u00A0/g, " ").trim();
};

const fmt = (iso) => {
  try {
    if (!iso) return "-";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "-";
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return "-";
  }
};

export default function PostDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { notification, showNotification, hideNotification } = useNotification();

  const [loading, setLoading] = useState(true);
  const [post, setPost] = useState(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const res = await callFunctionWithNaverAuth('getUserPosts');
        const found = (res?.posts || []).find((p) => p.id === id) || null;
        setPost(found);
        if (!found) {
          showNotification("해당 원고를 찾을 수 없습니다.", "warning");
        }
      } catch (e) {
        console.error(e);
        showNotification("원고를 불러오지 못했습니다.", "error");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id, showNotification]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(htmlToText(post?.content || ""));
      showNotification("본문을 클립보드에 복사했습니다.", "success");
    } catch (e) {
      console.error(e);
      showNotification("복사에 실패했습니다.", "error");
    }
  };

  return (
    <DashboardLayout title="원고 보기 (읽기 전용)">
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate(-1)}>
          뒤로
        </Button>
      </Stack>

      {loading ? (
        <Box sx={{ p: 6, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <CircularProgress />
        </Box>
      ) : !post ? (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography color="text.secondary">원고가 없습니다.</Typography>
        </Paper>
      ) : (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Alert severity="info" sx={{ mb: 2 }}>
            이 페이지는 <strong>읽기 전용</strong>입니다. 수정은 지원하지 않습니다.
            내용을 편집하려면 아래 <b>복사</b> 버튼으로 복사해 외부 편집기에서 수정하세요.
          </Alert>

          <Typography variant="h5" sx={{ mb: 1 }}>
            {post.title || "제목 없음"}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            생성일: {fmt(post.createdAt)} | 수정일: {fmt(post.updatedAt)} | 상태: {post.status || "draft"}
          </Typography>

          <Box
            sx={{
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
              p: 2,
              minHeight: 240,
              "& img": { maxWidth: "100%" },
              "& p": { m: 0, mb: 1.2 },
            }}
            dangerouslySetInnerHTML={{ __html: post.content || '<p>(내용 없음)</p>' }}
          />

          <Stack direction="row" spacing={1} sx={{ mt: 2 }} justifyContent="flex-end">
            <Button variant="contained" startIcon={<ContentCopyIcon />} onClick={handleCopy}>
              본문 복사
            </Button>
          </Stack>
        </Paper>
      )}

      <NotificationSnackbar
        open={notification.open}
        onClose={hideNotification}
        message={notification.message}
        severity={notification.severity}
        autoHideDuration={2200}
      />
    </DashboardLayout>
  );
}
