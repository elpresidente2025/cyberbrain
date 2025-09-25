// frontend/src/components/loading/LoadingSkeleton.jsx
import React from 'react';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableContainer, 
  TableHead, 
  TableRow,
  Box,
  Card,
  CardContent
} from '@mui/material';
import BaseSkeleton from './BaseSkeleton';
import { Skeleton as MUISkeleton } from '@mui/material';
// 하위 호환을 위한 별칭: 과거 코드가 Skeleton 식별자를 참조해도 동작하도록
const Skeleton = MUISkeleton || BaseSkeleton;

// 기본 스켈레톤
export const BasicSkeleton = ({ 
  variant = 'text', 
  width = '100%', 
  height = undefined,
  animation = 'pulse',
  sx = {},
  ...props
}) => (
  <BaseSkeleton 
    variant={variant} 
    width={width} 
    height={height} 
    animation={animation}
    sx={sx}
    {...props}
  />
);

// 테이블 스켈레톤
export const TableSkeleton = ({ 
  rows = 5, 
  columns = 4, 
  headers = [],
  showHeaders = true 
}) => (
  <TableContainer>
    <Table>
      {showHeaders && (
        <TableHead>
          <TableRow>
            {Array.from({ length: columns }).map((_, i) => (
              <TableCell key={i}>
              {headers[i] || <BaseSkeleton variant="text" width="80%" />}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
      )}
      <TableBody>
        {Array.from({ length: rows }).map((_, rowIndex) => (
          <TableRow key={rowIndex}>
            {Array.from({ length: columns }).map((_, colIndex) => (
              <TableCell key={colIndex}>
                <BaseSkeleton 
                  variant="text" 
                  width={colIndex === 0 ? '60%' : '80%'} 
                />
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </TableContainer>
);

// 카드 스켈레톤
export const CardSkeleton = ({ 
  count = 4,
  height = 150,
  showAvatar = false,
  showActions = false
}) => (
  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    {Array.from({ length: count }).map((_, index) => (
      <Card key={index}>
        <CardContent sx={{ p: 2 }}>
          {showAvatar && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
              <BaseSkeleton variant="circular" width={40} height={40} />
              <BaseSkeleton variant="text" width="30%" />
            </Box>
          )}
          <BaseSkeleton variant="text" width="60%" height={24} />
          <BaseSkeleton variant="text" width="100%" />
          <BaseSkeleton variant="text" width="80%" />
          {showActions && (
            <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
              <BaseSkeleton variant="rectangular" width={80} height={32} />
              <BaseSkeleton variant="rectangular" width={80} height={32} />
            </Box>
          )}
        </CardContent>
      </Card>
    ))}
  </Box>
);

// 대시보드 카드 스켈레톤
export const DashboardCardSkeleton = ({ count = 4 }) => (
  <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 2 }}>
    {Array.from({ length: count }).map((_, index) => (
      <Card key={index}>
        <CardContent sx={{ p: 2 }}>
          <BaseSkeleton variant="text" width="60%" />
          <BaseSkeleton variant="text" width="40%" height={40} />
          <BaseSkeleton variant="text" width="80%" />
        </CardContent>
      </Card>
    ))}
  </Box>
);

// 통합 스켈레톤 컴포넌트
const LoadingSkeleton = ({ 
  type = 'basic',
  ...props 
}) => {
  switch (type) {
    case 'table':
      return <TableSkeleton {...props} />;
    case 'card':
      return <CardSkeleton {...props} />;
    case 'dashboard':
      return <DashboardCardSkeleton {...props} />;
    case 'basic':
    default:
      return <BasicSkeleton {...props} />;
  }
};

export default LoadingSkeleton;
