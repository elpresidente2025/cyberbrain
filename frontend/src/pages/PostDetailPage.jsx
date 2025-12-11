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
import { NotificationSnackbar, useNotification } from '../components/ui';



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
        const res = await callFunctionWithNaverAuth('getPost', { postId: id });
        setPost(res?.post || null);
        if (!res?.post) {
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
          <Typography variant="h5" sx={{ mb: 1 }}>
            {post.title || "제목 없음"}
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
