// src/components/Editor.jsx
import React from "react";
import { Box, Alert, Stack, Button } from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";

const htmlToText = (html) => {
  if (!html) return "";
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  const text = tmp.textContent || tmp.innerText || "";
  return text.replace(/\u00A0/g, " ").trim();
};

const Editor = ({ initialContent }) => {
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(htmlToText(initialContent || ""));
      alert("본문을 클립보드에 복사했습니다.");
    } catch {
      alert("복사에 실패했습니다.");
    }
  };

  return (
    <Box>
      <Alert severity="info" sx={{ mb: 2 }}>
        이 구성요소는 <strong>읽기 전용</strong>입니다. 수정 기능은 제공하지 않습니다.
        복사 후 외부 편집기에서 수정하세요.
      </Alert>

      <Box
        sx={{
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
          p: 2,
          minHeight: 200,
          "& img": { maxWidth: "100%" },
          "& p": { m: 0, mb: 1.2 },
          backgroundColor: "#f5f5f5",
        }}
        dangerouslySetInnerHTML={{ __html: initialContent || "<p>(내용 없음)</p>" }}
      />

      <Stack direction="row" spacing={1} sx={{ mt: 2 }} justifyContent="flex-end">
        <Button variant="contained" startIcon={<ContentCopyIcon />} onClick={handleCopy}>
          본문 복사
        </Button>
      </Stack>
    </Box>
  );
};

export default Editor;
