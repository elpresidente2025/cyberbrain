// frontend/src/components/admin/LeadershipManager.jsx
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Button, TextField, Paper, CircularProgress,
  List, ListItemButton, ListItemText,
  Dialog, DialogTitle, DialogContent, DialogActions,
  Accordion, AccordionSummary, AccordionDetails,
  Alert, Snackbar, Chip, Divider, IconButton,
} from '@mui/material';
import { ExpandMore, Save, RestartAlt, Add, Delete, AutoStories, Close } from '@mui/icons-material';
import { callFunctionWithRetry } from '../../services/firebaseService';
import { colors } from '../../theme/tokens';

// ──────────────────────────────────────────────────────
// 메타데이터
// ──────────────────────────────────────────────────────

const DOMAIN_LABELS = {
  basicSociety: '기본사회', inclusiveNation: '포용국가',
  fairEconomy: '공정경제', peopleFirst: '민생우선', basicIncome: '기본소득',
};

const ARGUMENT_COLUMNS = {
  argument_chains:          { label: '논거체인',   fields: [['policy_domain','정책영역'],['logic','논리'],['connection','연결고리']] },
  empirical_evidence:       { label: '실증근거',   fields: [['claim','주장'],['source','출처']] },
  international_precedents: { label: '해외사례',   fields: [['country','국가'],['policy','정책'],['outcome','결과']] },
  counter_rebuttals:        { label: '반론재반박', fields: [['criticism','비판내용'],['rebuttal','재반박']] },
  korean_context:           { label: '한국적맥락', fields: [['context','맥락'],['implication','함의']] },
};

const ARG_TEMPLATES = {
  argument_chains:          { policy_domain: '', logic: '', connection: '' },
  empirical_evidence:       { claim: '', source: '' },
  international_precedents: { country: '', policy: '', outcome: '' },
  counter_rebuttals:        { criticism: '', rebuttal: '' },
  korean_context:           { context: '', implication: '' },
};

const SECTION_META = [
  { key: 'CORE_LEADERSHIP_VALUES', label: '핵심 리더십 가치', desc: '5대 핵심 가치 — 비전·원칙·정책·철학' },
  { key: 'LEADERSHIP_PHILOSOPHY',  label: '리더십 철학',     desc: '핵심원칙·정책접근·소통스타일' },
  { key: 'BALANCED_APPROACH',      label: '균형 접근법',     desc: '화해 균형점·건설적비판 프레임' },
  { key: 'PREFERRED_EXPRESSIONS',  label: '선호 표현',       desc: '핵심 키워드·자주 쓰는 구절·민생 어조' },
  { key: 'PRAGMATIC_EXPERIENCE',   label: '실용 경험',       desc: '성남·경기도 성과·교훈·검증방식' },
  { key: 'ARGUMENT_LAYER',         label: '논거 레이어',     desc: '5개 도메인 논거체인·실증근거·해외사례·반론재반박·한국적맥락', isComplex: true },
];

const TEXT_LIST_PATHS = {
  CORE_LEADERSHIP_VALUES: [
    'basicSociety.principles','basicSociety.policies',
    'inclusiveNation.principles','inclusiveNation.policies',
    'fairEconomy.principles','fairEconomy.policies',
    'peopleFirst.principles','peopleFirst.policies',
    'basicIncome.principles','basicIncome.policies',
  ],
  LEADERSHIP_PHILOSOPHY: [
    'policyApproach.pragmatic.characteristics',
    'policyApproach.evidenceBased.characteristics',
    'policyApproach.collaborative.characteristics',
  ],
  BALANCED_APPROACH: [
    'constructiveCriticism.process',
    'constructiveCriticism.principles',
  ],
  PREFERRED_EXPRESSIONS: [
    'coreKeywords.values','coreKeywords.policies','coreKeywords.philosophy',
    'frequentPhrases.opening','frequentPhrases.transition','frequentPhrases.policy','frequentPhrases.closing',
    'peopleFirstTone.characteristics','peopleFirstTone.examples',
  ],
  PRAGMATIC_EXPERIENCE: [
    'seongnamExperience.achievements','seongnamExperience.lessons',
    'gyeonggiExperience.achievements','gyeonggiExperience.lessons',
  ],
};

// ──────────────────────────────────────────────────────
// 경로 기반 getter / setter
// ──────────────────────────────────────────────────────

function pathGet(obj, pathStr) {
  let cur = obj;
  for (const p of pathStr.split('.')) cur = cur?.[p];
  return cur;
}

function pathSet(obj, pathStr, value) {
  const result = JSON.parse(JSON.stringify(obj));
  const parts = pathStr.split('.');
  let node = result;
  for (let i = 0; i < parts.length - 1; i++) node = node[parts[i]];
  node[parts[parts.length - 1]] = value;
  return result;
}

// ──────────────────────────────────────────────────────
// 정규화 / 역정규화
// ──────────────────────────────────────────────────────

function normalize(sectionKey, data) {
  let result = JSON.parse(JSON.stringify(data));
  for (const p of (TEXT_LIST_PATHS[sectionKey] || [])) {
    const val = pathGet(result, p);
    if (Array.isArray(val)) result = pathSet(result, p, val.join('\n'));
  }
  return result;
}

function denormalize(sectionKey, bufData) {
  let result = JSON.parse(JSON.stringify(bufData));
  for (const p of (TEXT_LIST_PATHS[sectionKey] || [])) {
    const val = pathGet(result, p);
    if (typeof val === 'string') {
      result = pathSet(result, p, val.split('\n').map(s => s.trim()).filter(Boolean));
    }
  }
  return result;
}

// ──────────────────────────────────────────────────────
// 공통 필드 컴포넌트
// ──────────────────────────────────────────────────────

const MULTILINE_FIELDS = new Set(['logic','connection','claim','outcome','criticism','rebuttal','context','implication']);

function FField({ label, value, onChange, multiline, helperText }) {
  return (
    <TextField
      label={label}
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      multiline={multiline}
      minRows={multiline ? 3 : 1}
      maxRows={multiline ? 10 : 1}
      size="small"
      fullWidth
      helperText={helperText}
      sx={{ mb: 1.5 }}
    />
  );
}

function ListField({ label, value, onChange }) {
  return (
    <FField label={label} value={value} onChange={onChange} multiline
      helperText="줄바꿈으로 항목을 구분합니다" />
  );
}

function SubPaper({ title, children }) {
  return (
    <Paper elevation={0} sx={{ p: 2, mb: 2, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
      {title && (
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1.5, color: 'text.secondary' }}>
          {title}
        </Typography>
      )}
      {children}
    </Paper>
  );
}

// ──────────────────────────────────────────────────────
// 섹션 렌더러 1 — 핵심 리더십 가치
// ──────────────────────────────────────────────────────

function renderCoreLeadershipValues(buf, sf) {
  return Object.entries(DOMAIN_LABELS).map(([key, label]) => (
    <SubPaper key={key} title={label}>
      <FField label="비전"    value={buf?.[key]?.vision}     onChange={v => sf(`${key}.vision`, v)} />
      <ListField label="원칙" value={buf?.[key]?.principles} onChange={v => sf(`${key}.principles`, v)} />
      <ListField label="정책" value={buf?.[key]?.policies}   onChange={v => sf(`${key}.policies`, v)} />
      <FField label="철학"    value={buf?.[key]?.philosophy} onChange={v => sf(`${key}.philosophy`, v)} />
    </SubPaper>
  ));
}

// ──────────────────────────────────────────────────────
// 섹션 렌더러 2 — 리더십 철학
// ──────────────────────────────────────────────────────

const CORE_PRINCIPLES = [
  ['humanCentered','사람이 우선'],['fieldBased','현장중심'],
  ['resultOriented','결과중심'],['inclusive','포용적접근'],
];
const POLICY_APPROACHES = [
  ['pragmatic','실용주의'],['evidenceBased','근거기반'],['collaborative','협력거버넌스'],
];
const TONE_LABELS = { warm: '따뜻함', humble: '겸손함', confident: '확신', empathetic: '공감' };
const METHOD_LABELS = { storytelling: '스토리텔링', datadriven: '데이터활용', futureoriented: '미래지향', actionable: '실행방안' };

function renderLeadershipPhilosophy(buf, sf) {
  return (
    <>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>핵심원칙</Typography>
      {CORE_PRINCIPLES.map(([k, label]) => (
        <SubPaper key={k} title={label}>
          <FField label="원칙" value={buf?.coreprinciples?.[k]?.principle}   onChange={v => sf(`coreprinciples.${k}.principle`, v)} />
          <FField label="의미" value={buf?.coreprinciples?.[k]?.meaning}     onChange={v => sf(`coreprinciples.${k}.meaning`, v)} />
          <FField label="적용" value={buf?.coreprinciples?.[k]?.application} onChange={v => sf(`coreprinciples.${k}.application`, v)} />
        </SubPaper>
      ))}
      <Divider sx={{ my: 2 }} />
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>정책접근</Typography>
      {POLICY_APPROACHES.map(([k, label]) => (
        <SubPaper key={k} title={label}>
          <FField label="스타일" value={buf?.policyApproach?.[k]?.style}          onChange={v => sf(`policyApproach.${k}.style`, v)} />
          <ListField label="특성" value={buf?.policyApproach?.[k]?.characteristics} onChange={v => sf(`policyApproach.${k}.characteristics`, v)} />
        </SubPaper>
      ))}
      <Divider sx={{ my: 2 }} />
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>소통 스타일</Typography>
      <SubPaper title="어조">
        {Object.entries(TONE_LABELS).map(([k, label]) => (
          <FField key={k} label={label} value={buf?.communicationStyle?.tone?.[k]} onChange={v => sf(`communicationStyle.tone.${k}`, v)} />
        ))}
      </SubPaper>
      <SubPaper title="방식">
        {Object.entries(METHOD_LABELS).map(([k, label]) => (
          <FField key={k} label={label} value={buf?.communicationStyle?.method?.[k]} onChange={v => sf(`communicationStyle.method.${k}`, v)} />
        ))}
      </SubPaper>
    </>
  );
}

// ──────────────────────────────────────────────────────
// 섹션 렌더러 3 — 균형 접근법
// ──────────────────────────────────────────────────────

const RECONCILIATION_KEYS = [
  ['ideologyVsPragmatism','이념 vs 실용'],['growthVsDistribution','성장 vs 분배'],
  ['efficiencyVsEquity','효율 vs 형평'],['centralVsLocal','중앙 vs 지방'],
];

function renderBalancedApproach(buf, sf) {
  return (
    <>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>화해 균형점</Typography>
      {RECONCILIATION_KEYS.map(([k, label]) => (
        <SubPaper key={k} title={label}>
          <FField label="접근" value={buf?.reconciliation?.[k]?.approach} onChange={v => sf(`reconciliation.${k}.approach`, v)} />
          <FField label="방법" value={buf?.reconciliation?.[k]?.method}   onChange={v => sf(`reconciliation.${k}.method`, v)} />
        </SubPaper>
      ))}
      <Divider sx={{ my: 2 }} />
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>건설적 비판</Typography>
      <ListField label="프로세스" value={buf?.constructiveCriticism?.process}    onChange={v => sf('constructiveCriticism.process', v)} />
      <ListField label="원칙"     value={buf?.constructiveCriticism?.principles} onChange={v => sf('constructiveCriticism.principles', v)} />
    </>
  );
}

// ──────────────────────────────────────────────────────
// 섹션 렌더러 4 — 선호 표현
// ──────────────────────────────────────────────────────

function renderPreferredExpressions(buf, sf) {
  return (
    <>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>핵심 키워드</Typography>
      <ListField label="가치어" value={buf?.coreKeywords?.values}    onChange={v => sf('coreKeywords.values', v)} />
      <ListField label="정책어" value={buf?.coreKeywords?.policies}  onChange={v => sf('coreKeywords.policies', v)} />
      <ListField label="철학어" value={buf?.coreKeywords?.philosophy} onChange={v => sf('coreKeywords.philosophy', v)} />
      <Divider sx={{ my: 2 }} />
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>자주 쓰는 구절</Typography>
      <ListField label="도입부" value={buf?.frequentPhrases?.opening}    onChange={v => sf('frequentPhrases.opening', v)} />
      <ListField label="전환"   value={buf?.frequentPhrases?.transition} onChange={v => sf('frequentPhrases.transition', v)} />
      <ListField label="정책"   value={buf?.frequentPhrases?.policy}     onChange={v => sf('frequentPhrases.policy', v)} />
      <ListField label="마무리" value={buf?.frequentPhrases?.closing}    onChange={v => sf('frequentPhrases.closing', v)} />
      <Divider sx={{ my: 2 }} />
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>민생중심 어조</Typography>
      <ListField label="특성" value={buf?.peopleFirstTone?.characteristics} onChange={v => sf('peopleFirstTone.characteristics', v)} />
      <ListField label="예시" value={buf?.peopleFirstTone?.examples}        onChange={v => sf('peopleFirstTone.examples', v)} />
    </>
  );
}

// ──────────────────────────────────────────────────────
// 섹션 렌더러 5 — 실용 경험
// ──────────────────────────────────────────────────────

const POLICY_VALIDATION_LABELS = { method: '방법', principle: '원칙', approach: '접근', expansion: '확산' };

function renderPragmaticExperience(buf, sf) {
  return (
    <>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>성남 경험</Typography>
      <ListField label="성과" value={buf?.seongnamExperience?.achievements} onChange={v => sf('seongnamExperience.achievements', v)} />
      <ListField label="교훈" value={buf?.seongnamExperience?.lessons}      onChange={v => sf('seongnamExperience.lessons', v)} />
      <Divider sx={{ my: 2 }} />
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>경기도 경험</Typography>
      <ListField label="성과" value={buf?.gyeonggiExperience?.achievements} onChange={v => sf('gyeonggiExperience.achievements', v)} />
      <ListField label="교훈" value={buf?.gyeonggiExperience?.lessons}      onChange={v => sf('gyeonggiExperience.lessons', v)} />
      <Divider sx={{ my: 2 }} />
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>정책 검증</Typography>
      {Object.entries(POLICY_VALIDATION_LABELS).map(([k, label]) => (
        <FField key={k} label={label} value={buf?.policyValidation?.[k]} onChange={v => sf(`policyValidation.${k}`, v)} />
      ))}
    </>
  );
}

// ──────────────────────────────────────────────────────
// 섹션 렌더러 6 — 논거 레이어
// ──────────────────────────────────────────────────────

function ArgumentItemCard({ item, fields, onEdit, onDelete }) {
  return (
    <Paper elevation={0} sx={{ p: 2, mb: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 1, position: 'relative' }}>
      <IconButton size="small" onClick={onDelete}
        sx={{ position: 'absolute', top: 6, right: 6, color: 'text.secondary' }}>
        <Delete fontSize="small" />
      </IconButton>
      <Box sx={{ pr: 4 }}>
        {fields.map(([fk, label]) => (
          <FField key={fk} label={label}
            value={item?.[fk] ?? ''}
            onChange={v => onEdit(fk, v)}
            multiline={MULTILINE_FIELDS.has(fk)}
          />
        ))}
      </Box>
    </Paper>
  );
}

function renderArgumentLayer(buf, setArgField, addArgItem, removeArgItem) {
  if (!buf) return null;
  return Object.entries(DOMAIN_LABELS).map(([domain, domainLabel]) => (
    <Accordion key={domain} disableGutters elevation={0}
      sx={{
        border: '1px solid',
        borderColor: 'divider',
        mb: 1,
        '&:before': { display: 'none' },
        '&.Mui-expanded': {
          borderColor: 'rgba(21, 36, 132, 0.3)',
          borderLeft: `2px solid ${colors.brand.primary}`,
        },
      }}>
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>{domainLabel}</Typography>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0 }}>
        {Object.entries(ARGUMENT_COLUMNS).map(([subKey, { label, fields }]) => {
          const items = buf?.[domain]?.[subKey] ?? [];
          return (
            <Box key={subKey} sx={{ mb: 3 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, mb: 1, color: 'text.secondary' }}>{label}</Typography>
              {items.map((item, idx) => (
                <ArgumentItemCard
                  key={idx}
                  item={item}
                  fields={fields}
                  onEdit={(fk, v) => setArgField(domain, subKey, idx, fk, v)}
                  onDelete={() => removeArgItem(domain, subKey, idx)}
                />
              ))}
              <Button size="small" startIcon={<Add />} variant="outlined"
                onClick={() => addArgItem(domain, subKey)}
                sx={{
                  mt: 0.5,
                  borderColor: 'rgba(21, 36, 132, 0.4)',
                  color: colors.brand.primary,
                  '&:hover': { borderColor: colors.brand.primary, bgcolor: 'rgba(21, 36, 132, 0.05)' },
                }}>
                항목 추가
              </Button>
            </Box>
          );
        })}
      </AccordionDetails>
    </Accordion>
  ));
}

// ──────────────────────────────────────────────────────
// 메인 컴포넌트
// ──────────────────────────────────────────────────────

export default function LeadershipManager({ open, onClose }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null);
  const [resetting, setResetting] = useState(null);
  const [overrideStatus, setOverrideStatus] = useState({});
  const [buffers, setBuffers] = useState({});
  const [selected, setSelected] = useState('CORE_LEADERSHIP_VALUES');
  const [notification, setNotification] = useState({ open: false, message: '', severity: 'info' });

  const showNotification = (message, severity = 'success') =>
    setNotification({ open: true, message, severity });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await callFunctionWithRetry('py_getLeadershipData', {});
      const normalized = {};
      for (const [k, v] of Object.entries(res.sections)) {
        normalized[k] = normalize(k, v);
      }
      setBuffers(normalized);
      setOverrideStatus(res.overrideStatus || {});
    } catch (err) {
      showNotification('데이터 로드 실패: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  // 모달이 열릴 때 데이터 로드
  useEffect(() => {
    if (open) loadData();
  }, [open, loadData]);

  const setField = useCallback((sectionKey, pathStr, value) => {
    setBuffers(prev => {
      const updated = JSON.parse(JSON.stringify(prev));
      updated[sectionKey] = pathSet(updated[sectionKey], pathStr, value);
      return updated;
    });
  }, []);

  const setArgField = useCallback((domain, subKey, idx, fk, value) => {
    setBuffers(prev => {
      const updated = JSON.parse(JSON.stringify(prev));
      updated.ARGUMENT_LAYER[domain][subKey][idx][fk] = value;
      return updated;
    });
  }, []);

  const addArgItem = useCallback((domain, subKey) => {
    setBuffers(prev => {
      const updated = JSON.parse(JSON.stringify(prev));
      updated.ARGUMENT_LAYER[domain][subKey].push({ ...ARG_TEMPLATES[subKey] });
      return updated;
    });
  }, []);

  const removeArgItem = useCallback((domain, subKey, idx) => {
    setBuffers(prev => {
      const updated = JSON.parse(JSON.stringify(prev));
      updated.ARGUMENT_LAYER[domain][subKey].splice(idx, 1);
      return updated;
    });
  }, []);

  const handleSave = async (sectionKey) => {
    setSaving(sectionKey);
    try {
      const payload = denormalize(sectionKey, buffers[sectionKey]);
      await callFunctionWithRetry('py_updateLeadershipSection', { section: sectionKey, data: payload });
      await loadData();
      showNotification('저장 완료', 'success');
    } catch (err) {
      showNotification('저장 실패: ' + err.message, 'error');
    } finally {
      setSaving(null);
    }
  };

  const handleReset = async (sectionKey) => {
    if (!window.confirm('기본값으로 초기화하면 저장된 편집 내용이 삭제됩니다. 계속하시겠습니까?')) return;
    setResetting(sectionKey);
    try {
      await callFunctionWithRetry('py_resetLeadershipSection', { section: sectionKey });
      await loadData();
      showNotification('기본값으로 초기화했습니다', 'success');
    } catch (err) {
      showNotification('초기화 실패: ' + err.message, 'error');
    } finally {
      setResetting(null);
    }
  };

  const sectionContent = (meta) => {
    const buf = buffers[meta.key];
    if (!buf) return null;
    const sf = (pathStr, value) => setField(meta.key, pathStr, value);
    switch (meta.key) {
      case 'CORE_LEADERSHIP_VALUES': return renderCoreLeadershipValues(buf, sf);
      case 'LEADERSHIP_PHILOSOPHY':  return renderLeadershipPhilosophy(buf, sf);
      case 'BALANCED_APPROACH':      return renderBalancedApproach(buf, sf);
      case 'PREFERRED_EXPRESSIONS':  return renderPreferredExpressions(buf, sf);
      case 'PRAGMATIC_EXPERIENCE':   return renderPragmaticExperience(buf, sf);
      case 'ARGUMENT_LAYER':         return renderArgumentLayer(buf, setArgField, addArgItem, removeArgItem);
      default: return null;
    }
  };

  const selectedMeta = SECTION_META.find(m => m.key === selected);
  const overrideCount = Object.values(overrideStatus).filter(Boolean).length;

  return (
    <>
      <Dialog
        open={open}
        onClose={onClose}
        fullWidth
        maxWidth="lg"
        PaperProps={{
          sx: {
            height: '88vh',
            display: 'flex',
            flexDirection: 'column',
            m: { xs: 1, sm: 2 },
            maxHeight: { xs: 'calc(100% - 16px)', sm: 'calc(100% - 32px)' },
          },
        }}
      >
        {/* 헤더 */}
        <DialogTitle
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1.5,
            py: 2,
            px: 3,
            borderBottom: '1px solid',
            borderColor: 'divider',
            flexShrink: 0,
          }}
        >
          <AutoStories sx={{ color: colors.brand.primary, fontSize: 22 }} />
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, color: colors.brand.primary, lineHeight: 1.2 }}>
              리더십 철학 관리
            </Typography>
            {overrideCount > 0 && (
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                {overrideCount}개 섹션 오버레이 적용 중
              </Typography>
            )}
          </Box>
          <Button
            size="small"
            variant="outlined"
            onClick={loadData}
            disabled={loading}
            sx={{ mr: 1, borderColor: 'divider', color: 'text.secondary', '&:hover': { borderColor: 'text.primary' } }}
          >
            새로고침
          </Button>
          <IconButton onClick={onClose} size="small" aria-label="닫기">
            <Close />
          </IconButton>
        </DialogTitle>

        {/* 본문 */}
        <DialogContent sx={{ display: 'flex', p: 0, overflow: 'hidden', flex: 1 }}>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', width: '100%' }}>
              <CircularProgress />
            </Box>
          ) : (
            <>
              {/* 좌측 네비게이션 */}
              <Box
                sx={{
                  width: { xs: 160, sm: 210 },
                  flexShrink: 0,
                  borderRight: '1px solid',
                  borderColor: 'divider',
                  overflowY: 'auto',
                  bgcolor: 'action.hover',
                }}
              >
                <List dense disablePadding>
                  {SECTION_META.map((meta) => (
                    <ListItemButton
                      key={meta.key}
                      selected={selected === meta.key}
                      onClick={() => setSelected(meta.key)}
                      sx={{
                        py: 1.5,
                        px: { xs: 1.5, sm: 2 },
                        borderLeft: '3px solid',
                        borderLeftColor: selected === meta.key
                          ? colors.brand.primary
                          : 'transparent',
                        transition: 'border-color 0.15s',
                        '&.Mui-selected': {
                          bgcolor: 'rgba(21, 36, 132, 0.08)',
                        },
                        '&.Mui-selected:hover': {
                          bgcolor: 'rgba(21, 36, 132, 0.12)',
                        },
                      }}
                    >
                      <ListItemText
                        primary={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
                            <span>{meta.label}</span>
                            {overrideStatus[meta.key] && (
                              <Chip
                                label="적용"
                                size="small"
                                sx={{
                                  height: 15,
                                  fontSize: '0.58rem',
                                  bgcolor: 'rgba(21, 36, 132, 0.1)',
                                  color: colors.brand.primary,
                                  border: '1px solid rgba(21, 36, 132, 0.25)',
                                  '& .MuiChip-label': { px: 0.75 },
                                }}
                              />
                            )}
                          </Box>
                        }
                        secondary={meta.desc}
                        primaryTypographyProps={{
                          variant: 'body2',
                          fontWeight: selected === meta.key ? 600 : 400,
                          sx: { lineHeight: 1.3 },
                        }}
                        secondaryTypographyProps={{
                          variant: 'caption',
                          sx: {
                            fontSize: '0.62rem',
                            lineHeight: 1.3,
                            mt: 0.3,
                            display: 'block',
                            wordBreak: 'keep-all',
                          },
                        }}
                      />
                    </ListItemButton>
                  ))}
                </List>
              </Box>

              {/* 우측 콘텐츠 패널 */}
              <Box
                sx={{
                  flex: 1,
                  overflowY: 'auto',
                  p: { xs: 2, sm: 3 },
                }}
              >
                {selectedMeta && (
                  <>
                    <Box sx={{ mb: 3 }}>
                      <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
                        {selectedMeta.label}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {selectedMeta.desc}
                      </Typography>
                    </Box>
                    {sectionContent(selectedMeta)}
                  </>
                )}
              </Box>
            </>
          )}
        </DialogContent>

        {/* 액션 영역 */}
        <DialogActions
          sx={{
            px: 3,
            py: 2,
            borderTop: '1px solid',
            borderColor: 'divider',
            flexShrink: 0,
            gap: 1,
          }}
        >
          <Button
            variant="outlined"
            color="warning"
            size="small"
            disabled={!overrideStatus[selected] || resetting === selected}
            onClick={() => handleReset(selected)}
            startIcon={resetting === selected ? <CircularProgress size={14} /> : <RestartAlt />}
          >
            기본값으로 초기화
          </Button>
          <Box sx={{ flex: 1 }} />
          <Button size="small" onClick={onClose} sx={{ color: 'text.secondary' }}>
            닫기
          </Button>
          <Button
            variant="contained"
            size="small"
            disabled={saving === selected}
            onClick={() => handleSave(selected)}
            startIcon={saving === selected ? <CircularProgress size={14} /> : <Save />}
            sx={{ bgcolor: colors.brand.primary, '&:hover': { bgcolor: '#1e30a0' } }}
          >
            저장
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={notification.open}
        autoHideDuration={4000}
        onClose={() => setNotification(p => ({ ...p, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={notification.severity} onClose={() => setNotification(p => ({ ...p, open: false }))}>
          {notification.message}
        </Alert>
      </Snackbar>
    </>
  );
}
