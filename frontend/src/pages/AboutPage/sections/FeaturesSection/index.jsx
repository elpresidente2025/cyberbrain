// E:\ai-secretary\frontend\src\pages\AboutPage\sections\FeaturesSection\index.jsx
// Features section - core features display

import React from 'react';
import { Typography, Grid, CardContent } from '@mui/material';
import { Section, ContentContainer, CardSoft } from '../../components/StyledComponents';
import { CORE_FEATURES } from '../../data';
import InViewFade from '../../components/InViewFade';

function FeaturesSection() {
  return (
    <Section id="how" aria-labelledby="features-heading">
      <ContentContainer maxWidth="lg">
        <InViewFade>
          <Typography id="features-heading" variant="h4" sx={{ fontWeight: 800, mb: 6 }}>
            핵심 기능
          </Typography>
        </InViewFade>
        <Grid container spacing={3}>
          {CORE_FEATURES.map((f, idx) => (
            <Grid item xs={12} md={6} key={f.title}>
              <InViewFade timeout={600 + idx * 80}>
                <CardSoft>
                  <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>
                      {f.title}
                    </Typography>
                    <Typography sx={{ mt: 1.25 }}>
                      {f.desc}
                    </Typography>
                  </CardContent>
                </CardSoft>
              </InViewFade>
            </Grid>
          ))}
        </Grid>
      </ContentContainer>
    </Section>
  );
}

export default FeaturesSection;
