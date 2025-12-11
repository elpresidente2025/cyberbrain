// frontend/src/pages/GuidelinesPage.jsx
import React, { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Container,
  Typography,
  Paper,
  Box,
  Grid,
  Card,
  CardContent,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Chip,
  Alert,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  TextField,
  InputAdornment,
  useTheme
} from '@mui/material';
import {
  Edit,
  Dashboard,
  List as ListIcon,
  CheckCircleOutline,
  Warning,
  TrendingUp,
  ExpandMore,
  Search,
  Person
} from '@mui/icons-material';
import DashboardLayout from '../components/DashboardLayout';
import { colors } from '../theme/tokens';
import GenerateGuide from '../components/guides/GenerateGuide';
import DashboardGuide from '../components/guides/DashboardGuide';
import ManagementGuide from '../components/guides/ManagementGuide';
import ChecklistGuide from '../components/guides/ChecklistGuide';
import UsageGuide from '../components/guides/UsageGuide';
import ProfileGuide from '../components/guides/ProfileGuide';

const GuidelinesPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedAccordion, setExpandedAccordion] = useState('generate');
  const theme = useTheme();

  const handleAccordionChange = (panel) => (event, isExpanded) => {
    setExpandedAccordion(isExpanded ? panel : false);
  };

  const guideData = [
    {
      id: 'generate',
      title: '원고 생성하기',
      icon: <Edit sx={{ color: colors.brand.primary }} />,
      component: <GenerateGuide />
    },
    {
      id: 'dashboard',
      title: '대시보드 활용',
      icon: <Dashboard sx={{ color: colors.brand.primary }} />,
      component: <DashboardGuide />
    },
    {
      id: 'management',
      title: '원고 관리',
      icon: <ListIcon sx={{ color: colors.brand.primary }} />,
      component: <ManagementGuide />
    },
    {
      id: 'checklist',
      title: '사용 전 체크포인트',
      icon: <CheckCircleOutline sx={{ color: '#4caf50' }} />,
      component: <ChecklistGuide />
    },
    {
      id: 'usage',
      title: '월간 사용량 관리',
      icon: <TrendingUp sx={{ color: '#2196f3' }} />,
      component: <UsageGuide />
    },
    {
      id: 'profile',
      title: '프로필 설정',
      icon: <Person sx={{ color: '#9c27b0' }} />,
      component: <ProfileGuide />
    }
  ];

  const filteredGuides = searchQuery 
    ? guideData.filter(guide => 
        guide.title.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : guideData;


  return (
    <DashboardLayout title="전자두뇌비서관 사용 가이드">
      <Box sx={{ height: 20 }} />
      <Container maxWidth="xl">
        {/* 페이지 헤더 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <Box sx={{ mb: 4 }}>
            <Typography variant="h4" sx={{
              fontWeight: 'bold',
              mb: 1,
              color: theme.palette.mode === 'dark' ? 'white' : 'black'
            }}>
              전자두뇌비서관 사용 가이드
            </Typography>
            <Typography variant="body1" sx={{ color: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.6)' }}>
              AI로 정치 콘텐츠를 효과적으로 생성하고 관리하는 방법을 안내합니다
            </Typography>
          </Box>
        </motion.div>

        {/* 검색 기능 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <Paper sx={{ p: 2, mb: 3 }}>
          <TextField
            fullWidth
            placeholder="궁금한 내용을 검색해보세요 (예: 원고 생성, 대시보드, 관리)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <Search sx={{ color: '#666' }} />
                </InputAdornment>
              ),
            }}
            sx={{
              '& .MuiOutlinedInput-root': {
                '& fieldset': { borderColor: '#ddd' },
                '&:hover fieldset': { borderColor: colors.brand.primary },
                '&.Mui-focused fieldset': { borderColor: colors.brand.primary }
              }
            }}
          />
        </Paper>
        </motion.div>

        {/* 가이드 아코디언 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
        >
          <Box>
          {filteredGuides.map((guide) => (
            <Accordion
              key={guide.id}
              expanded={expandedAccordion === guide.id}
              onChange={handleAccordionChange(guide.id)}
              sx={{ 
                mb: 2, 
                border: theme.palette.mode === 'dark' 
                  ? '1px solid rgba(255, 255, 255, 0.1)' 
                  : '1px solid #ddd', 
                borderRadius: '2px !important' 
              }}
            >
              <AccordionSummary
                expandIcon={<ExpandMore />}
                sx={{ 
                  bgcolor: theme.palette.mode === 'dark' 
                    ? 'rgba(255, 255, 255, 0.05)' 
                    : '#f8f9fa',
                  borderRadius: expandedAccordion === guide.id ? '2px 2px 0 0' : '2px'
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  {guide.icon}
                  <Typography variant="h6" sx={{ ml: 2, fontWeight: 600 }}>
                    {guide.title}
                  </Typography>
                </Box>
              </AccordionSummary>
              
              <AccordionDetails sx={{ p: 3 }}>
                {guide.component}
              </AccordionDetails>
            </Accordion>
          ))}
        </Box>
        </motion.div>

        {/* 검색 결과 없음 */}
        {filteredGuides.length === 0 && (
          <Paper sx={{ p: 4, textAlign: 'center' }}>
            <Typography variant="h6" color="text.secondary">
              검색 결과가 없습니다
            </Typography>
            <Typography variant="body2" color="text.secondary">
              다른 키워드로 검색해보세요
            </Typography>
          </Paper>
        )}
        
        <Box sx={{ height: 20 }} />
      </Container>
    </DashboardLayout>
  );
};

export default GuidelinesPage;