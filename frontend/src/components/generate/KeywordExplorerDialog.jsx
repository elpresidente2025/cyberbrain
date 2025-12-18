// frontend/src/components/generate/KeywordExplorerDialog.jsx

import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Box,
  Typography,
  Chip,
  CircularProgress,
  Alert,
  Grid,
  Paper,
  IconButton,
  Tooltip,
  LinearProgress
} from '@mui/material';
import {
  Search,
  Close,
  TrendingUp,
  ContentCopy,
  Add
} from '@mui/icons-material';
import { httpsCallable } from 'firebase/functions';
import { functions, auth } from '../../services/firebase';
import { colors, spacing } from '../../theme/tokens';

const KeywordExplorerDialog = ({ open, onClose, onSelectKeyword, topic, instructions, user }) => {
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [analysisId, setAnalysisId] = useState(null);

  // 다이얼로그가 열릴 때 자동으로 분석 시작
  useEffect(() => {
    if (open && topic) {
      handleAutoSearch();
    }
  }, [open]);

  const handleAutoSearch = async () => {
    console.log('🔍 KeywordExplorer - user:', user);
    console.log('🔍 KeywordExplorer - topic:', topic);
    console.log('🔍 KeywordExplorer - instructions:', instructions);

    // 사용자 인증 확인
    if (!user || !user.uid) {
      setError('로그인이 필요합니다. 다시 로그인해주세요.');
      return;
    }

    // district는 프로필에서만 가져옴
    const district = user?.district || '전국';
    console.log('🔍 KeywordExplorer - district:', district);

    // topic 확인
    if (!topic || !topic.trim()) {
      setError('주제를 먼저 입력해주세요');
      return;
    }

    // 주제와 참고자료를 합쳐서 상세 정보 생성
    const topicDetail = topic.trim();
    const additionalContext = [];

    if (instructions && Array.isArray(instructions)) {
      instructions.forEach(inst => {
        if (inst && inst.trim()) {
          additionalContext.push(inst.trim());
        }
      });
    }

    // topic에 참고자료 내용을 추가
    const fullTopic = additionalContext.length > 0
      ? `${topicDetail} ${additionalContext.join(' ')}`
      : topicDetail;

    console.log('🔍 KeywordExplorer - fullTopic:', fullTopic.substring(0, 200));

    setLoading(true);
    setError(null);
    setResults(null);

    try {
      // 1. 분석 요청 - 네이버 인증 방식으로 전송
      const requestAnalysis = httpsCallable(functions, 'requestKeywordAnalysis');
      const response = await requestAnalysis({
        district: district,
        topic: fullTopic.substring(0, 1000), // 최대 1000자
        __naverAuth: {
          uid: user.uid,
          provider: user.provider || 'naver'
        }
      });

      const { taskId: newTaskId } = response.data;
      setAnalysisId(newTaskId);

      // 2. 결과 폴링 시작
      setLoading(false);
      setPolling(true);
      pollResults(newTaskId);
    } catch (err) {
      console.error('검색어 추천 요청 실패:', err);
      setError('검색어 추천 요청에 실패했습니다. 다시 시도해주세요.');
      setLoading(false);
    }
  };

  const pollResults = async (taskId) => {
    const getResult = httpsCallable(functions, 'getKeywordAnalysisResult');
    const maxAttempts = 60; // 최대 60초 폴링 (AI 분석에 시간이 더 필요할 수 있음)
    let attempts = 0;

    const poll = async () => {
      if (attempts >= maxAttempts) {
        setError('분석 시간이 초과되었습니다. 다시 시도해주세요.');
        setPolling(false);
        return;
      }

      try {
        const response = await getResult({
          taskId,
          __naverAuth: {
            uid: user.uid,
            provider: user.provider || 'naver'
          }
        });
        const data = response.data;

        console.log('🔍 KeywordExplorer - poll result:', data);

        if (data.status === 'completed') {
          setResults({
            keywords: data.keywords,
            metadata: {
              timestamp: data.completedAt || new Date().toISOString(),
              cached: data.fromCache || false
            }
          });
          setPolling(false);
        } else if (data.status === 'failed') {
          setError(data.error || '분석에 실패했습니다.');
          setPolling(false);
        } else {
          // 아직 처리 중
          attempts++;
          setTimeout(poll, 1000); // 1초 후 재시도
        }
      } catch (err) {
        console.error('결과 조회 실패:', err);
        setError('결과 조회에 실패했습니다.');
        setPolling(false);
      }
    };

    poll();
  };

  const handleKeywordSelect = (keyword) => {
    if (onSelectKeyword) {
      onSelectKeyword(keyword);
    }
    handleClose();
  };

  const handleClose = () => {
    setResults(null);
    setError(null);
    setAnalysisId(null);
    setLoading(false);
    setPolling(false);
    onClose();
  };

  const getScoreColor = (score) => {
    if (score >= 80) return '#4caf50'; // 녹색
    if (score >= 60) return colors.brand.primary; // 파랑
    if (score >= 40) return '#ff9800'; // 주황
    return '#f44336'; // 빨강
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth slotProps={{ backdrop: { 'aria-hidden': false } }}>
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Search sx={{ color: colors.brand.primary }} />
            <Typography variant="h6">검색어 추천</Typography>
          </Box>
          <IconButton onClick={handleClose}>
            <Close />
          </IconButton>
        </Box>
      </DialogTitle>

      <DialogContent>
        {/* 안내 메시지 */}
        <Alert severity="info" sx={{ mb: 3 }}>
          입력하신 주제와 참고자료를 기반으로 노출에 유리한 검색어를 AI가 추천합니다.
        </Alert>

        {/* 로딩 상태 */}
        {(loading || polling) && (
          <Box sx={{ mb: 3 }}>
            <LinearProgress />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1, textAlign: 'center' }}>
              {loading ? '분석 요청 중...' : 'AI가 검색어를 분석하고 있습니다... (최대 30초 소요)'}
            </Typography>
          </Box>
        )}

        {/* 에러 메시지 */}
        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}

        {/* 분석 결과 */}
        {results && (
          <Box>
            <Typography variant="h6" sx={{ mb: 2 }}>
              추천 검색어
            </Typography>

            {results.keywords && results.keywords.length > 0 ? (
              <Grid container spacing={2}>
                {results.keywords.slice(0, 12).map((item, index) => (
                  <Grid item xs={12} sm={6} md={4} key={index}>
                    <Paper
                      elevation={0}
                      sx={{
                        p: 2,
                        cursor: 'pointer',
                        border: '1px solid',
                        borderColor: 'divider',
                        transition: 'all 0.2s',
                        '&:hover': {
                          borderColor: colors.brand.primary,
                          boxShadow: `0 0 8px ${colors.brand.primary}40`,
                          transform: 'translateY(-2px)'
                        }
                      }}
                      onClick={() => handleKeywordSelect(item.keyword)}
                    >
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                        <Typography variant="body1" sx={{ fontWeight: 600, flexGrow: 1 }}>
                          {item.keyword}
                        </Typography>
                        <Chip
                          label={Math.round(item.score)}
                          size="small"
                          sx={{
                            bgcolor: getScoreColor(item.score),
                            color: 'white',
                            fontWeight: 'bold',
                            minWidth: '40px'
                          }}
                        />
                      </Box>

                      {item.trendScore !== undefined && (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 1 }}>
                          <TrendingUp sx={{ fontSize: 16, color: 'text.secondary' }} />
                          <Typography variant="caption" color="text.secondary">
                            트렌드: {item.trendScore > 0 ? `+${item.trendScore}%` : `${item.trendScore}%`}
                          </Typography>
                        </Box>
                      )}

                      <Box sx={{ mt: 1 }}>
                        <Tooltip title="노출 희망 검색어에 추가">
                          <IconButton
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleKeywordSelect(item.keyword);
                            }}
                          >
                            <Add fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </Paper>
                  </Grid>
                ))}
              </Grid>
            ) : (
              <Alert severity="info">
                추천할 검색어를 찾지 못했습니다. 주제를 더 구체적으로 입력해보세요.
              </Alert>
            )}

            {/* 분석 메타 정보 */}
            {results.metadata && (
              <Box sx={{ mt: 3, p: 2, bgcolor: 'rgba(0,0,0,0.02)', borderRadius: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  분석 완료: {new Date(results.metadata.timestamp).toLocaleString('ko-KR')}
                  {results.metadata.cached && ' (캐시됨)'}
                </Typography>
              </Box>
            )}
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={handleClose}>닫기</Button>
      </DialogActions>
    </Dialog>
  );
};

export default KeywordExplorerDialog;
