import { useTheme, useMediaQuery, Button } from '@mui/material';
import { Computer } from '@mui/icons-material';

export default function MobileToPCBanner() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  const handleKakaoShare = () => {
    // 안내 메시지 표시
    if (!window.confirm('카카오톡으로 링크를 공유하여\nPC에서 접속하시겠습니까?')) {
      return;
    }

    if (!window.Kakao || !window.Kakao.isInitialized()) {
      alert('카카오톡 공유 기능을 불러오는 중입니다. 잠시 후 다시 시도해주세요.');
      return;
    }

    try {
      window.Kakao.Share.sendDefault({
        objectType: 'feed',
        content: {
          title: '전자두뇌비서관',
          description: 'PC에서 더 편리하게 이용하세요!',
          imageUrl: 'https://ai-secretary-6e9c8.web.app/logo-landscape.png',
          link: {
            mobileWebUrl: window.location.href,
            webUrl: window.location.href
          }
        },
        buttons: [
          {
            title: 'PC에서 열기',
            link: {
              mobileWebUrl: window.location.href,
              webUrl: window.location.href
            }
          }
        ]
      });
    } catch (err) {
      console.error('카카오톡 공유 실패:', err);
      alert('카카오톡 공유에 실패했습니다.');
    }
  };

  if (!isMobile) return null;

  return (
    <Button
      variant="contained"
      size="small"
      startIcon={<Computer />}
      onClick={handleKakaoShare}
      sx={{
        bgcolor: '#FFD400',
        color: '#000000',
        fontWeight: 'bold',
        fontSize: '0.75rem',
        py: 0.5,
        px: 1.5,
        '&:hover': {
          bgcolor: '#FFC700'
        }
      }}
    >
      PC 접속
    </Button>
  );
}
