'use strict';

import React from 'react';
import { Box, Typography, Divider, List, ListItem, ListItemText } from '@mui/material';

const TermsPage = () => {
  return (
    <Box sx={{ maxWidth: 960, mx: 'auto', px: { xs: 2, md: 4 }, py: 6 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        이용약관 및 개인정보 처리방침
      </Typography>

      <Typography variant="body1" gutterBottom>
        본 서비스는 생성형 AI 기반 콘텐츠 작성 지원 도구입니다. 아래 약관과 개인정보 처리방침을 확인하시고
        동의하신 뒤 이용해주세요.
      </Typography>

      <Divider sx={{ my: 3 }} />

      <Typography variant="h5" component="h2" gutterBottom>
        이용약관(요약)
      </Typography>
      <List dense>
        <ListItem>
          <ListItemText
            primary="목적"
            secondary="서비스를 통해 정치·정책 관련 콘텐츠 작성 및 관리 기능을 제공합니다."
          />
        </ListItem>
        <ListItem>
          <ListItemText
            primary="계정 및 보안"
            secondary="사용자는 본인 확인을 위해 제공된 인증 수단을 사용해야 하며, 계정 및 인증 정보 관리 책임은 사용자에게 있습니다."
          />
        </ListItem>
        <ListItem>
          <ListItemText
            primary="사용자 콘텐츠"
            secondary="사용자가 입력·업로드한 자료는 서비스 제공과 품질 개선을 위해 활용될 수 있으며, 법령과 본 약관을 준수해야 합니다."
          />
        </ListItem>
        <ListItem>
          <ListItemText
            primary="금지 사항"
            secondary="타인의 권리를 침해하거나 불법·유해한 정보를 게시하는 행위를 금지합니다. 위반 시 서비스 이용이 제한될 수 있습니다."
          />
        </ListItem>
        <ListItem>
          <ListItemText
            primary="서비스 변경"
            secondary="서비스는 예고 후 변경·중단될 수 있으며, 불가피한 장애 발생 시 신속히 복구를 위해 노력합니다."
          />
        </ListItem>
      </List>

      <Divider sx={{ my: 3 }} />

      <Typography variant="h5" component="h2" gutterBottom>
        개인정보 처리방침(요약)
      </Typography>
      <List dense>
        <ListItem>
          <ListItemText
            primary="수집 항목"
            secondary="필수: 이메일/계정 식별 정보, 인증 정보. 선택: 프로필·Bio·업로드 자료 등 서비스 기능 수행에 필요한 정보."
          />
        </ListItem>
        <ListItem>
          <ListItemText
            primary="이용 목적"
            secondary="콘텐츠 생성 지원, 계정 관리, 보안(이상 탐지), 결제/청구, 고객 지원 및 서비스 품질 개선."
          />
        </ListItem>
        <ListItem>
          <ListItemText
            primary="보관 및 파기"
            secondary="관련 법령이 정한 기간 동안만 보관하며, 목적이 달성되면 지체 없이 안전하게 파기합니다."
          />
        </ListItem>
        <ListItem>
          <ListItemText
            primary="제3자 제공"
            secondary="법령에 따른 요구 또는 명시적 동의가 있는 경우를 제외하고 제3자에게 제공하지 않습니다."
          />
        </ListItem>
        <ListItem>
          <ListItemText
            primary="이용자 권리"
            secondary="사용자는 개인정보 열람·정정·삭제·처리정지 등을 요청할 수 있으며, 문의 시 신속히 대응합니다."
          />
        </ListItem>
      </List>

      <Divider sx={{ my: 3 }} />

      <Typography variant="body2" color="text.secondary">
        ※ 본 요약은 이해를 돕기 위한 것입니다. 자세한 내용은 관리자에게 요청하거나 서비스 공지에서
        전체 약관과 개인정보 처리방침을 확인해주세요.
      </Typography>
    </Box>
  );
};

export default TermsPage;
