// E:\ai-secretary\frontend\src\pages\AboutPage\sections\StatsSection\index.jsx
// Stats section - key performance indicators

import React from 'react';
import { Box, Container, Typography, Grid, Card, CardContent } from '@mui/material';
import { STATS_DATA } from '../../data';
import InViewFade from '../../components/InViewFade';

function StatsSection() {
  return (
    <Box component="section" id="stats" sx={{
      py: 10,
      scrollSnapAlign: 'start',
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center'
    }}>
      <Container>
        <InViewFade>
          <Typography variant="h4" sx={{ fontWeight: 800, textAlign: 'center', mb: 6 }}>
            핵심 성과 지표
          </Typography>
        </InViewFade>
        <Grid container spacing={6}>
          {STATS_DATA.map((stat, idx) => (
            <Grid item xs={12} sm={4} md={4} key={stat.title}>
              <InViewFade timeout={600 + idx * 100}>
                <Card sx={{
                  bgcolor: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(0, 212, 255, 0.2)',
                  borderRadius: 0.75,
                  height: '100%',
                  transition: 'all 0.3s ease',
                  '&:hover': {
                    borderColor: 'rgba(0, 212, 255, 0.5)',
                    transform: 'translateY(-8px)',
                    boxShadow: '0 12px 40px rgba(0, 212, 255, 0.2)'
                  }
                }}>
                  <CardContent sx={{ p: { xs: 3, sm: 2, md: 3, lg: 4 }, textAlign: 'center' }}>
                    <Typography variant="h2" sx={{
                      fontWeight: 900,
                      color: '#00d4ff',
                      mb: 0.5,
                      fontSize: { xs: '3.5rem', sm: '3rem', md: '3.5rem', lg: '4.5rem' },
                      lineHeight: 1
                    }}>
                      {stat.number}
                      <Typography component="span" variant="h4" sx={{
                        ml: 1,
                        color: 'rgba(255,255,255,0.8)',
                        fontWeight: 700,
                        fontSize: { xs: '1.8rem', sm: '1.5rem', md: '1.8rem', lg: '2.2rem' }
                      }}>
                        {stat.unit}
                      </Typography>
                    </Typography>
                    <Typography variant="subtitle2" sx={{
                      color: 'rgba(255,255,255,0.5)',
                      mb: 2,
                      fontWeight: 500,
                      fontSize: { xs: '0.75rem', sm: '0.65rem', md: '0.7rem', lg: '0.75rem' }
                    }}>
                      {stat.title}
                    </Typography>
                    <Typography sx={{
                      color: '#00d4ff',
                      mb: 1,
                      fontSize: { xs: '0.95rem', sm: '0.75rem', md: '0.85rem', lg: '0.95rem' },
                      fontWeight: 600,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis'
                    }}>
                      {stat.description}
                    </Typography>
                    <Typography variant="body2" sx={{
                      color: 'rgba(255,255,255,0.5)',
                      fontSize: { xs: '0.8rem', sm: '0.65rem', md: '0.7rem', lg: '0.8rem' },
                      lineHeight: 1.4
                    }}>
                      {stat.subtext}
                    </Typography>
                  </CardContent>
                </Card>
              </InViewFade>
            </Grid>
          ))}
        </Grid>
      </Container>
    </Box>
  );
}

export default StatsSection;
