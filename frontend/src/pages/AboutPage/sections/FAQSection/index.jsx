// E:\ai-secretary\frontend\src\pages\AboutPage\sections\FAQSection\index.jsx
// FAQ section - frequently asked questions

import React from 'react';
import {
  Typography,
  Stack,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Section, ContentContainer } from '../../components/StyledComponents';
import { FAQS } from '../../data';
import InViewFade from '../../components/InViewFade';

function FAQSection({ expandedFaq, handleAccordionChange }) {
  return (
    <Section aria-labelledby="faq-heading">
      <ContentContainer maxWidth="lg">
        <InViewFade>
          <Typography id="faq-heading" variant="h4" sx={{ fontWeight: 800, mb: 4 }}>
            자주 묻는 질문
          </Typography>
        </InViewFade>
        <Stack spacing={2}>
          {FAQS.map((item, i) => (
            <InViewFade key={item.q} timeout={600 + i * 80}>
              <Accordion
                disableGutters
                expanded={expandedFaq === `panel${i}`}
                onChange={handleAccordionChange(`panel${i}`)}
                sx={{ backgroundColor: 'rgba(255,255,255,0.04)', borderRadius: 2, '&::before': { display: 'none' } }}
              >
                <AccordionSummary
                  expandIcon={<ExpandMoreIcon sx={{ color: '#00d4ff' }} />}
                  aria-controls={`faq-${i}-content`}
                  id={`faq-${i}-header`}
                  sx={{ px: 3, py: 2 }}
                >
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    {item.q}
                  </Typography>
                </AccordionSummary>
                <AccordionDetails sx={{ px: 3, pb: 3 }}>
                  <Typography sx={{ mb: 2, fontWeight: 600, color: '#00d4ff' }}>
                    {item.a}
                  </Typography>
                  {item.detail && (
                    <Typography sx={{ color: 'rgba(255,255,255,0.8)', lineHeight: 1.6 }}>
                      {item.detail}
                    </Typography>
                  )}
                </AccordionDetails>
              </Accordion>
            </InViewFade>
          ))}
        </Stack>
      </ContentContainer>
    </Section>
  );
}

export default FAQSection;
