// frontend/src/components/admin/ActiveUsersChartModal.jsx
import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  IconButton,
  Box,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  CircularProgress,
  Alert
} from '@mui/material';
import { Close } from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';
import { getActiveUserStats } from '../../services/firebaseService';

const PERIOD_OPTIONS = [
  { value: 'week', label: '주간' },
  { value: 'month', label: '월간' },
  { value: 'year', label: '연간' }
];

function ActiveUsersChartModal({ open, onClose }) {
  const [period, setPeriod] = useState('week');
  const [data, setData] = useState([]);
  const [uniqueUsers, setUniqueUsers] = useState(0);
  const [totalActivity, setTotalActivity] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const isMountedRef = useRef(true);

  const fetchData = useCallback(async (selectedPeriod) => {
    setLoading(true);
    setError(null);

    try {
      const result = await getActiveUserStats(selectedPeriod);

      if (isMountedRef.current) {
        if (result.success && result.data) {
          setData(result.data.stats || []);
          setUniqueUsers(result.data.uniqueUsers || 0);
          setTotalActivity(result.data.totalActivity || 0);
        } else if (result.stats) {
          setData(result.stats);
          setUniqueUsers(result.uniqueUsers || 0);
          setTotalActivity(result.totalActivity || 0);
        } else {
          setData([]);
          setUniqueUsers(0);
          setTotalActivity(0);
        }
      }
    } catch (err) {
      console.error('활성 사용자 통계 조회 실패:', err);
      if (isMountedRef.current) {
        setError(err.message || '데이터를 불러오는데 실패했습니다.');
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;

    if (open) {
      fetchData(period);
    }

    return () => {
      isMountedRef.current = false;
    };
  }, [open, period, fetchData]);

  const handlePeriodChange = useCallback((event, newPeriod) => {
    if (newPeriod !== null) {
      setPeriod(newPeriod);
    }
  }, []);

  // 날짜 포맷 함수
  const formatDate = useCallback((dateStr) => {
    const date = new Date(dateStr);
    const month = date.getMonth() + 1;
    const day = date.getDate();
    return `${month}/${day}`;
  }, []);

  // 연간의 경우 월 단위로 그룹핑
  const chartData = useMemo(() => {
    if (period === 'year' && data.length > 0) {
      // 월별로 그룹핑
      const monthlyData = {};
      data.forEach(item => {
        const date = new Date(item.date);
        const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
        if (!monthlyData[monthKey]) {
          monthlyData[monthKey] = { date: monthKey, count: 0 };
        }
        monthlyData[monthKey].count += item.count;
      });
      return Object.values(monthlyData).map(item => ({
        ...item,
        displayDate: `${parseInt(item.date.split('-')[1])}월`
      }));
    }
    return data.map(item => ({
      ...item,
      displayDate: formatDate(item.date)
    }));
  }, [data, period, formatDate]);

  // 통계 요약
  const summary = useMemo(() => {
    if (chartData.length === 0) return null;
    const total = chartData.reduce((sum, d) => sum + d.count, 0);
    const max = Math.max(...chartData.map(d => d.count));
    const avg = total / chartData.length;
    return { total, max, avg: avg.toFixed(1) };
  }, [chartData]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      aria-labelledby="active-users-chart-title"
    >
      <DialogTitle
        id="active-users-chart-title"
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          pb: 1
        }}
      >
        <Typography variant="h6" component="span">
          활성 사용자 추이
        </Typography>
        <IconButton
          onClick={onClose}
          aria-label="닫기"
          sx={{
            '&:focus-visible': {
              outline: '2px solid #006261',
              outlineOffset: '2px'
            }
          }}
        >
          <Close />
        </IconButton>
      </DialogTitle>

      <DialogContent>
        {/* 기간 선택 */}
        <Box sx={{ display: 'flex', justifyContent: 'center', mb: 3 }}>
          <ToggleButtonGroup
            value={period}
            exclusive
            onChange={handlePeriodChange}
            aria-label="기간 선택"
            size="small"
          >
            {PERIOD_OPTIONS.map(option => (
              <ToggleButton
                key={option.value}
                value={option.value}
                aria-pressed={period === option.value}
                sx={{
                  '&:focus-visible': {
                    outline: '2px solid #006261',
                    outlineOffset: '2px'
                  }
                }}
              >
                {option.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Box>

        {/* 로딩 상태 */}
        {loading && (
          <Box
            sx={{ display: 'flex', justifyContent: 'center', py: 8 }}
            aria-busy="true"
            aria-label="데이터 로딩 중"
          >
            <CircularProgress />
          </Box>
        )}

        {/* 에러 상태 */}
        {error && !loading && (
          <Alert severity="error" role="alert" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {/* 차트 */}
        {!loading && !error && chartData.length > 0 && (
          <>
            {/* 요약 통계 */}
            <Box
              sx={{
                display: 'flex',
                justifyContent: 'center',
                gap: { xs: 2, sm: 4 },
                mb: 2,
                flexWrap: 'wrap'
              }}
              role="region"
              aria-label="요약 통계"
            >
              <Box sx={{ textAlign: 'center', minWidth: 80 }}>
                <Typography variant="caption" color="text.secondary">
                  고유 사용자
                </Typography>
                <Typography variant="h6" sx={{ color: '#006261', fontWeight: 'bold' }}>
                  {uniqueUsers}명
                </Typography>
              </Box>
              <Box sx={{ textAlign: 'center', minWidth: 80 }}>
                <Typography variant="caption" color="text.secondary">
                  총 활동
                </Typography>
                <Typography variant="h6">{totalActivity}회</Typography>
              </Box>
              {summary && (
                <>
                  <Box sx={{ textAlign: 'center', minWidth: 80 }}>
                    <Typography variant="caption" color="text.secondary">
                      일 최고
                    </Typography>
                    <Typography variant="h6">{summary.max}명</Typography>
                  </Box>
                  <Box sx={{ textAlign: 'center', minWidth: 80 }}>
                    <Typography variant="caption" color="text.secondary">
                      일 평균
                    </Typography>
                    <Typography variant="h6">{summary.avg}명</Typography>
                  </Box>
                </>
              )}
            </Box>

            {/* 차트 영역 */}
            <Box
              sx={{ width: '100%', height: 300 }}
              role="img"
              aria-label={`활성 사용자 ${period === 'week' ? '주간' : period === 'month' ? '월간' : '연간'} 추이 그래프`}
            >
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={chartData}
                  margin={{ top: 5, right: 20, left: 0, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                  <XAxis
                    dataKey="displayDate"
                    tick={{ fontSize: 12 }}
                    tickMargin={8}
                  />
                  <YAxis
                    tick={{ fontSize: 12 }}
                    tickMargin={8}
                    allowDecimals={false}
                  />
                  <Tooltip
                    formatter={(value) => [`${value}명`, '활성 사용자']}
                    labelFormatter={(label) => `날짜: ${label}`}
                    contentStyle={{
                      backgroundColor: '#fff',
                      border: '1px solid #ccc',
                      borderRadius: 4
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="count"
                    stroke="#006261"
                    strokeWidth={2}
                    dot={{ fill: '#006261', strokeWidth: 2, r: 4 }}
                    activeDot={{ r: 6, fill: '#00847c' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </>
        )}

        {/* 데이터 없음 */}
        {!loading && !error && chartData.length === 0 && (
          <Box sx={{ textAlign: 'center', py: 8 }}>
            <Typography color="text.secondary">
              해당 기간의 데이터가 없습니다.
            </Typography>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default ActiveUsersChartModal;
