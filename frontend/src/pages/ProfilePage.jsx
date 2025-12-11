// frontend/src/pages/ProfilePage.jsx
import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Box,
  Button,
  TextField,
  Typography,
  Paper,
  Container,
  Alert,
  Grid,
  IconButton,
  Tooltip,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Card,
  CardContent,
  CardActions,
  Chip,
  Divider,
  Stack,
  FormControlLabel,
  Checkbox,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  useTheme
} from '@mui/material';
import { Add, Remove, AutoAwesome, DeleteForever, Warning, Settings, Save } from '@mui/icons-material';
import { callFunctionWithNaverAuth } from '../services/firebaseService';
import DashboardLayout from '../components/DashboardLayout';
import UserInfoForm from '../components/UserInfoForm';
import ProfileBioGuideModal from '../components/onboarding/ProfileBioGuideModal';
import CongratulationsModal from '../components/onboarding/CongratulationsModal';
import { LoadingSpinner, LoadingButton } from '../components/loading';
import { useAuth } from '../hooks/useAuth';
import { BIO_ENTRY_TYPES, BIO_TYPE_ORDER, BIO_CATEGORIES, VALIDATION_RULES } from '../constants/bio-types';
import {
  LoadingState,
  StandardDialog,
  PageHeader,
  ActionButton,
  NotificationSnackbar,
  useNotification,
  ContentCard
} from '../components/ui';
import { colors, spacing, typography, visualWeight, verticalRhythm } from '../theme/tokens';

export default function ProfilePage() {
  const { user, logout } = useAuth();
  const theme = useTheme();
  
  // 상태 관리

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // useNotification 훅 사용
  const { notification, showNotification, hideNotification } = useNotification();
  
  // 회원탈퇴 다이얼로그 상태
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [deleting, setDeleting] = useState(false);

  // 온보딩 가이드 모달 상태
  const [bioGuideOpen, setBioGuideOpen] = useState(false);
  const [congratulationsOpen, setCongratulationsOpen] = useState(false);
  const [isFirstTimeBioSave, setIsFirstTimeBioSave] = useState(false);

  const [profile, setProfile] = useState({
    name: '',
    status: '현역',
    position: '',
    regionMetro: '',
    regionLocal: '',
    electoralDistrict: '',
    bio: '',
    customTitle: '', // 준비 상태일 때 사용할 직위
    // 개인화 정보 (선택사항)
    ageDecade: '',
    ageDetail: '',
    familyStatus: '',
    backgroundCareer: '',
    localConnection: '',
    politicalExperience: '',
    gender: '',
    twitterPremium: false,
    committees: [''],
    customCommittees: [],
    constituencyType: '',
  });

  // DB에 실제 저장된 직위 값 (배지 표시용)
  const [savedCustomTitle, setSavedCustomTitle] = useState('');


  // 회원탈퇴 처리
  const handleDeleteAccount = async () => {
    if (deleteConfirmText !== '회원탈퇴') {
      showNotification('확인 문구를 정확히 입력해주세요.', 'error');
      return;
    }

    setDeleting(true);
    try {
      console.log('회원탈퇴 시작...');
      await callFunctionWithNaverAuth('deleteUserAccount');

      showNotification('회원탈퇴가 완료되었습니다. 그동안 이용해 주셔서 감사합니다.', 'success');

      // 잠시 후 로그아웃 처리
      setTimeout(async () => {
        try {
          await logout();
        } catch (logoutError) {
          console.error('로그아웃 오류:', logoutError);
          window.location.href = '/login';
        }
      }, 2000);

    } catch (error) {
      console.error('회원탈퇴 오류:', error);
      let errorMessage = '회원탈퇴 처리 중 오류가 발생했습니다.';

      if (error.code === 'unauthenticated') {
        errorMessage = '로그인이 필요합니다.';
      } else if (error.message) {
        errorMessage = error.message;
      }

      showNotification(errorMessage, 'error');
    } finally {
      setDeleting(false);
      setDeleteDialogOpen(false);
      setDeleteConfirmText('');
    }
  };

  const handleCloseDeleteDialog = () => {
    setDeleteDialogOpen(false);
    setDeleteConfirmText('');
  };


  // Bio 엔트리 상태 관리
  const [bioEntries, setBioEntries] = useState([
    {
      id: 'entry_initial',
      type: 'self_introduction',
      title: '자기소개',
      content: '',
      tags: [],
      weight: 1.0
    },
    {
      id: 'entry_additional_default',
      type: 'policy',
      title: '',
      content: '',
      tags: [],
      weight: 1.0
    }
  ]);

  // 프로필 다시 불러오기 함수 (저장 후 서버 값 확인용)
  const reloadProfile = async () => {
    try {
      const res = await callFunctionWithNaverAuth('getUserProfile');
      let profileData = res?.profile || res || {};

      const newProfile = {
        name: profileData.name || profileData.displayName || '',
        status: profileData.status || '현역',
        position: profileData.position || '',
        regionMetro: profileData.regionMetro || '',
        regionLocal: profileData.regionLocal || '',
        electoralDistrict: profileData.electoralDistrict || '',
        bio: profileData.bio || '',
        customTitle: profileData.customTitle || '',
        // 개인화 정보 (선택사항)
        ageDecade: profileData.ageDecade || '',
        ageDetail: profileData.ageDetail || '',
        familyStatus: profileData.familyStatus || '',
        backgroundCareer: profileData.backgroundCareer || '',
        localConnection: profileData.localConnection || '',
        politicalExperience: profileData.politicalExperience || '',
        gender: profileData.gender || '',
        twitterPremium: profileData.twitterPremium || false,
        committees: profileData.committees || [''],
        customCommittees: profileData.customCommittees || [],
        constituencyType: profileData.constituencyType || '',
      };

      setProfile(newProfile);

      // bioEntries 복원 (서버에서 받아온 값이 있으면 사용)
      if (profileData.bioEntries && Array.isArray(profileData.bioEntries)) {
        console.log('🔍 [reloadProfile] bioEntries 복원:', { count: profileData.bioEntries.length });
        setBioEntries(profileData.bioEntries);
      } else {
        // bioEntries가 없으면 기본값으로 초기화
        console.log('🔍 [reloadProfile] bioEntries 없음 - 기본값 사용');
        if (newProfile.bio && newProfile.bio.trim()) {
          setBioEntries([
            {
              id: 'entry_initial',
              type: 'self_introduction',
              title: '자기소개',
              content: newProfile.bio.trim(),
              tags: [],
              weight: 1.0
            },
            {
              id: 'entry_additional_default',
              type: 'policy',
              title: '',
              content: '',
              tags: [],
              weight: 1.0
            }
          ]);
        } else {
          setBioEntries([
            {
              id: 'entry_initial',
              type: 'self_introduction',
              title: '자기소개',
              content: '',
              tags: [],
              weight: 1.0
            },
            {
              id: 'entry_additional_default',
              type: 'policy',
              title: '',
              content: '',
              tags: [],
              weight: 1.0
            }
          ]);
        }
      }

      // DB에 저장된 실제 값 업데이트 (배지 표시용)
      const savedTitle = profileData.customTitle || '';
      console.log('🔍 [reloadProfile] customTitle 업데이트:', {
        raw: profileData.customTitle,
        saved: savedTitle,
        willUpdate: savedTitle
      });
      setSavedCustomTitle(savedTitle);

      // localStorage의 사용자 정보도 서버 데이터로 업데이트
      try {
        const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
        const updatedUser = {
          ...currentUser,
          ...newProfile,
          bio: profileData.bio || ''
        };
        localStorage.setItem('currentUser', JSON.stringify(updatedUser));
        console.log('✅ ProfilePage: 프로필 리로드 완료 (customTitle:', newProfile.customTitle, ')');

        window.dispatchEvent(new CustomEvent('userProfileUpdated', {
          detail: updatedUser
        }));
      } catch (e) {
        console.warn('ProfilePage: localStorage 업데이트 실패:', e);
      }

      return newProfile;
    } catch (error) {
      console.error('프로필 리로드 실패:', error);
      throw error;
    }
  };

  // 최초 로드
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setLoading(true);

        const newProfile = await reloadProfile();

        if (!mounted) return;

        // bioEntries는 reloadProfile에서 이미 초기화됨 (중복 제거)

        // bio가 없는 경우 가이드 모달 표시 (온보딩에서 넘어온 경우)
        const hasSufficientBio = newProfile.bio && newProfile.bio.trim().length >= 200;
        if (!hasSufficientBio) {
          console.log('🎯 Profile 페이지 - Bio 가이드 모달 표시', {
            bio: newProfile.bio,
            length: newProfile.bio?.length || 0,
            hasSufficientBio
          });
          // 페이지 로딩 완료 후 잠시 뒤에 글로우 효과와 함께 모달 표시 (자연스러운 UX)
          setTimeout(() => {
            console.log('🎯 Bio 가이드 - 글로우 효과 시작');
            focusBioTextarea();
          }, 800);
        } else {
          console.log('🎯 충분한 Bio가 있어서 가이드 모달 표시하지 않음', {
            bio: newProfile.bio?.substring(0, 50) + '...',
            length: newProfile.bio?.length || 0
          });
        }
        
      } catch (e) {
        console.error('[getUserProfile 오류]', e);
        setError('프로필 정보를 불러오지 못했습니다: ' + (e.message || '알 수 없는 오류'));
      } finally {
        setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  // UserInfoForm 컴포넌트에서 오는 변경사항 처리
  const handleUserInfoChange = (name, value) => {
    setError('');
    setProfile((prev) => ({ ...prev, [name]: value }));
  };

  // 직위 즉시 저장 핸들러 (추가/삭제 시 즉시 DB에 저장)
  const handleCustomTitleSave = async (newCustomTitle, action = 'save') => {
    try {
      setSaving(true);
      console.log('🔄 직위 즉시 저장:', newCustomTitle, '액션:', action);

      const payload = {
        customTitle: newCustomTitle
      };

      const res = await callFunctionWithNaverAuth('updateProfile', payload);
      console.log('updateProfile 응답:', res);

      if (res) {
        // 서버에서 저장된 프로필 다시 불러오기
        await reloadProfile();
        console.log('✅ 직위 저장 후 프로필 리로드 완료');

        // 액션에 따라 다른 메시지 표시
        if (action === 'delete') {
          showNotification('직위가 삭제되었습니다.', 'success');
        } else {
          showNotification('직위가 저장되었습니다.', 'success');
        }
      } else {
        throw new Error('서버 응답이 올바르지 않습니다.');
      }
    } catch (e) {
      console.error('[직위 저장 오류]', e);
      setError('직위 저장 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.');
      // 실패 시 프로필 다시 불러와서 UI와 DB 동기화
      await reloadProfile();
    } finally {
      setSaving(false);
    }
  };

  // 자기소개 카드에 순차적으로 스크롤->글로우 2회->팝업 효과를 주는 함수
  const focusBioTextarea = () => {
    // 첫 번째 bio 엔트리의 카드 찾기 (자기소개 섹션)
    const bioCard = document.querySelector('[data-bio-section="personal"]');
    if (bioCard) {
      // 1단계: 카드를 화면 중앙으로 스크롤
      bioCard.scrollIntoView({
        behavior: 'smooth',
        block: 'center'
      });

      // 2단계: 스크롤 완료 직후 글로우 효과 2회 반복 (0.5초 후 시작)
      setTimeout(() => {
        let glowCount = 0;
        const maxGlows = 2;

        const glowCycle = () => {
          if (glowCount >= maxGlows) {
            // 모든 글로우 완료 후 모달 표시
            setBioGuideOpen(true);
            return;
          }

          // 글로우 효과 적용 (시안색, 부드러운 강도)
          bioCard.style.position = 'relative';
          bioCard.style.zIndex = '100';
          bioCard.style.boxShadow = '0 0 15px 3px rgba(0, 188, 212, 0.5), 0 0 25px 8px rgba(0, 188, 212, 0.2)';
          bioCard.style.borderRadius = '12px';
          bioCard.style.transition = 'all 0.3s ease';
          bioCard.style.transform = 'scale(1.01)';

          // 0.3초 후 글로우 제거
          setTimeout(() => {
            bioCard.style.position = '';
            bioCard.style.zIndex = '';
            bioCard.style.boxShadow = '';
            bioCard.style.transform = '';

            glowCount++;

            // 0.2초 후 다음 글로우 또는 완료
            setTimeout(glowCycle, 200);
          }, 300);
        };

        // 첫 번째 글로우 시작
        glowCycle();
      }, 500);
    } else {
      // 카드를 찾지 못한 경우 바로 모달 표시
      setBioGuideOpen(true);
    }
  };

  // 자기소개 변경 처리 (기존 호환성)
  const handleBioChange = (e) => {
    const { value } = e.target;
    setError('');
    setProfile((prev) => ({ ...prev, bio: value }));

    // Bio 엔트리의 첫 번째 항목(자기소개)도 동기화
    setBioEntries(prev => prev.map((entry, index) =>
      index === 0 ? { ...entry, content: value } : entry
    ));
  };

  // Bio 엔트리 변경 핸들러
  const handleBioEntryChange = (index, field, value) => {
    setBioEntries(prev => prev.map((entry, i) => 
      i === index ? { ...entry, [field]: value } : entry
    ));
    
    // 첫 번째 엔트리(자기소개)면 기존 bio 필드도 동기화
    if (index === 0 && field === 'content') {
      setProfile(prev => ({ ...prev, bio: value }));
    }
    setError('');
  };

  // 카테고리별 Bio 엔트리 필터링
  const getEntriesByCategory = (category) => {
    if (category === 'PERSONAL') {
      return bioEntries.filter(entry => 
        BIO_CATEGORIES.PERSONAL.types.some(type => type.id === entry.type)
      );
    }
    if (category === 'PERFORMANCE') {
      return bioEntries.filter(entry => 
        BIO_CATEGORIES.PERFORMANCE.types.some(type => type.id === entry.type)
      );
    }
    return [];
  };

  // Bio 엔트리 추가 (카테고리별)
  const addBioEntry = (category = 'PERFORMANCE') => {
    if (bioEntries.length >= VALIDATION_RULES.maxEntries) {
      setError(`최대 ${VALIDATION_RULES.maxEntries}개의 엔트리까지 추가 가능합니다.`);
      return;
    }

    let defaultType = 'policy';
    if (category === 'PERSONAL') {
      defaultType = 'vision';
    }

    const newEntry = {
      id: `entry_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      type: defaultType,
      title: '',
      content: '',
      tags: [],
      weight: 1.0
    };

    setBioEntries(prev => [...prev, newEntry]);
  };

  // Bio 엔트리 삭제
  const removeBioEntry = (index) => {
    if (index === 0) {
      setError('자기소개는 삭제할 수 없습니다.');
      return;
    }
    
    setBioEntries(prev => prev.filter((_, i) => i !== index));
  };

  // 검증
  const validate = () => {
    const bioTrim = (profile.bio || '').trim();
    if (!bioTrim) {
      setError('자기소개는 필수입니다. 간단히라도 본인을 설명해 주세요.');
      return false;
    }
    if (bioTrim.length < 10) {
      setError('자기소개가 너무 짧습니다. 최소 10자 이상 입력해 주세요. (권장: 100~300자)');
      return false;
    }

    // 기본 필수 정보 체크
    if (!profile.name || !profile.position || !profile.regionMetro) {
      setError('모든 필수 정보를 입력해 주세요.');
      return false;
    }

    // 직책별 필수 정보 체크
    if (profile.position === '광역자치단체장') {
      // 광역자치단체장: regionMetro만 필요
      // 추가 검증 없음
    } else if (profile.position === '기초자치단체장') {
      // 기초자치단체장: regionLocal까지 필요
      if (!profile.regionLocal) {
        setError('기초자치단체를 선택해 주세요.');
        return false;
      }
    } else {
      // 의원: regionLocal, electoralDistrict 모두 필요
      if (!profile.regionLocal || !profile.electoralDistrict) {
        setError('모든 필수 정보를 입력해 주세요.');
        return false;
      }
    }

    return true;
  };

  // 기본 프로필 정보만 저장
  const handleProfileSubmit = async (e) => {
    e.preventDefault();
    setError('');

    console.log('프로필 정보 저장 시작...');

    // 기본 필수 정보만 체크
    if (!profile.name || !profile.position || !profile.regionMetro) {
      setError('모든 필수 정보를 입력해 주세요.');
      return;
    }

    // 직책별 필수 정보 체크
    if (profile.position === '기초자치단체장' && !profile.regionLocal) {
      setError('기초자치단체를 선택해 주세요.');
      return;
    } else if (profile.position !== '광역자치단체장' && profile.position !== '기초자치단체장') {
      if (!profile.regionLocal || !profile.electoralDistrict) {
        setError('모든 필수 정보를 입력해 주세요.');
        return;
      }
    }

    try {
      setSaving(true);

      const payload = {
        name: profile.name,
        status: profile.status,
        customTitle: profile.customTitle,
        position: profile.position,
        regionMetro: profile.regionMetro,
        regionLocal: profile.regionLocal,
        electoralDistrict: profile.electoralDistrict,
      };

      console.log('전송할 프로필 데이터:', JSON.stringify(payload, null, 2));

      const res = await callFunctionWithNaverAuth('updateProfile', payload);
      console.log('updateProfile 응답:', res);

      if (res) {
        // 서버에서 저장된 프로필 다시 불러오기 (저장 확인)
        try {
          await reloadProfile();
          console.log('✅ 기본정보 저장 후 프로필 리로드 완료 (서버 값 확인)');
        } catch (reloadError) {
          console.warn('프로필 리로드 실패:', reloadError);
          // 리로드 실패해도 저장은 성공했으므로 계속 진행
        }

        showNotification('프로필 정보가 저장되었습니다.', 'success');
      } else {
        throw new Error('서버 응답이 올바르지 않습니다.');
      }

    } catch (e) {
      console.error('[프로필 저장 오류]', e);

      let errorMessage = '저장 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.';
      const actualMessage = e?.message || e?.details?.message || '';

      if (actualMessage.includes('선거구') || actualMessage.includes('사용 중')) {
        errorMessage = '해당 선거구는 이미 다른 사용자가 사용 중입니다.';
      } else if (e.code === 'functions/already-exists') {
        errorMessage = '해당 선거구에는 이미 등록된 사용자가 있습니다.';
      }

      setError(errorMessage);
    } finally {
      setSaving(false);
    }
  };

  // 자기소개 및 추가 정보만 저장
  const handleBioSubmit = async (e) => {
    e.preventDefault();
    setError('');

    console.log('자기소개 정보 저장 시작...');

    // bio 최소 길이 체크
    const bioTrim = (profile.bio || '').trim();
    if (bioTrim.length > 0 && bioTrim.length < 10) {
      setError('자기소개가 너무 짧습니다. 최소 10자 이상 입력해 주세요.');
      return;
    }

    try {
      setSaving(true);

      // 첫 번째 bio 저장인지 체크
      const hadSufficientBio = user?.bio && user.bio.trim().length >= 200;
      const willHaveSufficientBio = profile.bio && profile.bio.trim().length >= 200;
      const isFirstBioCompletion = !hadSufficientBio && willHaveSufficientBio;

      if (isFirstBioCompletion) {
        console.log('🎯 첫 번째 자기소개 완성 감지');
        setIsFirstTimeBioSave(true);
      }

      const payload = {
        bio: profile.bio,
        customTitle: profile.customTitle,
        bioEntries: bioEntries, // 정책/공약 등 추가 정보 엔트리
        ageDecade: profile.ageDecade,
        ageDetail: profile.ageDetail,
        familyStatus: profile.familyStatus,
        backgroundCareer: profile.backgroundCareer,
        localConnection: profile.localConnection,
        politicalExperience: profile.politicalExperience,
        gender: profile.gender,
        twitterPremium: profile.twitterPremium,
        committees: profile.committees,
        customCommittees: profile.customCommittees,
        constituencyType: profile.constituencyType,
      };

      console.log('전송할 자기소개 데이터:', JSON.stringify(payload, null, 2));
      console.log('🔍 [저장] bioEntries:', bioEntries.length, '개');

      const res = await callFunctionWithNaverAuth('updateProfile', payload);
      console.log('updateProfile 응답:', res);

      if (res) {
        // 서버에서 저장된 프로필 다시 불러오기 (저장 확인)
        try {
          await reloadProfile();
          console.log('✅ 자기소개 저장 후 프로필 리로드 완료 (서버 값 확인)');
        } catch (reloadError) {
          console.warn('프로필 리로드 실패:', reloadError);
          // 리로드 실패해도 저장은 성공했으므로 계속 진행
        }

        // 첫 번째 bio 완성인 경우 축하 모달 표시
        if (isFirstBioCompletion) {
          console.log('🎉 첫 번째 bio 완성 - 축하 모달 표시');
          setCongratulationsOpen(true);
        } else {
          showNotification('자기소개 및 추가 정보가 저장되었습니다.', 'success');
        }
      } else {
        throw new Error('서버 응답이 올바르지 않습니다.');
      }

    } catch (e) {
      console.error('[자기소개 저장 오류]', e);
      setError('저장 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.');
    } finally {
      setSaving(false);
    }
  };

  // 전체 정보 저장 (기존 함수 유지)
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    console.log('폼 제출 시작...');

    if (!validate()) return;

    try {
      setSaving(true);

      // 첫 번째 bio 저장인지 체크 (기존에 bio가 없었고, 새로 200자 이상 작성한 경우)
      const hadSufficientBio = user?.bio && user.bio.trim().length >= 200;
      const willHaveSufficientBio = profile.bio && profile.bio.trim().length >= 200;
      const isFirstBioCompletion = !hadSufficientBio && willHaveSufficientBio;

      if (isFirstBioCompletion) {
        console.log('🎯 첫 번째 자기소개 완성 감지');
        setIsFirstTimeBioSave(true);
      }

      const payload = {
        name: profile.name,
        status: profile.status,
        position: profile.position,
        regionMetro: profile.regionMetro,
        regionLocal: profile.regionLocal,
        electoralDistrict: profile.electoralDistrict,
        bio: profile.bio,
        customTitle: profile.customTitle,
        // 개인화 정보 필드들 추가
        ageDecade: profile.ageDecade,
        ageDetail: profile.ageDetail,
        familyStatus: profile.familyStatus,
        backgroundCareer: profile.backgroundCareer,
        localConnection: profile.localConnection,
        politicalExperience: profile.politicalExperience,
        gender: profile.gender,
        twitterPremium: profile.twitterPremium,
        committees: profile.committees,
        customCommittees: profile.customCommittees,
        constituencyType: profile.constituencyType,
      };
      
      console.log('전송할 데이터 (전체):', JSON.stringify(payload, null, 2));
      console.log('🔍 [저장] customTitle 값:', payload.customTitle);

      const res = await callFunctionWithNaverAuth('updateProfile', payload);
      console.log('updateProfile 응답:', res);
      
      // callFunctionWithNaverAuth는 이미 .data를 반환하므로 직접 사용
      if (res) {
        let message = '프로필이 저장되었습니다.';
        if (res.message) {
          message = res.message;
        }

        // 서버에서 저장된 프로필 다시 불러오기 (저장 확인)
        try {
          await reloadProfile();
          console.log('✅ 저장 후 프로필 리로드 완료 (서버 값 확인)');
        } catch (reloadError) {
          console.warn('프로필 리로드 실패:', reloadError);
          // 리로드 실패해도 저장은 성공했으므로 계속 진행
        }

        // 첫 번째 bio 완성인 경우 축하 모달 표시
        if (isFirstBioCompletion) {
          console.log('🎉 첫 번째 bio 완성 - 축하 모달 표시');
          setCongratulationsOpen(true);
        } else {
          showNotification(message, 'success');
        }
      } else {
        throw new Error('서버 응답이 올바르지 않습니다.');
      }
      
    } catch (e) {
      console.error('[updateProfile 오류 - 전체 객체]', {
        error: e,
        code: e?.code,
        message: e?.message,
        details: e?.details,
        customData: e?.customData
      });
      
      // 사용자 친화적인 에러 메시지
      let errorMessage = '저장 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.';
      
      // 다양한 경로로 오는 에러 메시지 체크
      const actualMessage = e?.message || e?.details?.message || '';
      console.log('[오류 메시지 분석]', { actualMessage });
      
      // 선거구 중복 관련 메시지 우선 체크
      if (actualMessage.includes('선거구') || actualMessage.includes('사용 중') || actualMessage.includes('다른 사용자')) {
        errorMessage = '해당 선거구는 이미 다른 사용자가 사용 중입니다. 다른 선거구를 선택해주세요.';
      } else if (e.code === 'functions/already-exists') {
        errorMessage = '해당 선거구에는 이미 등록된 사용자가 있습니다. 다른 선거구를 선택해주세요.';
      } else if (e.code === 'functions/failed-precondition') {
        errorMessage = actualMessage || '선거구 정보 업데이트에 실패했습니다.';
      } else if (e.code === 'functions/not-found') {
        errorMessage = '일시적으로 서비스에 접속할 수 없습니다. 잠시 후 다시 시도해주세요.';
      } else if (e.code === 'functions/unauthenticated') {
        errorMessage = '로그인이 만료되었습니다. 다시 로그인해주세요.';
      } else if (e.code === 'functions/internal') {
        errorMessage = '서버에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요.';
      } else if (e.code === 'functions/permission-denied') {
        errorMessage = '권한이 없습니다. 관리자에게 문의해주세요.';
      } else if (e.message && e.message.includes('CORS')) {
        errorMessage = '서비스 연결에 문제가 있습니다. 잠시 후 다시 시도해주세요.';
      } else if (e.details?.message) {
        errorMessage = e.details.message;
      } else if (e.message) {
        // 메시지 내용 기반 에러 처리 (백업용)
        if (e.message.includes('already exists') || e.message.includes('중복') || e.message.includes('사용 중')) {
          errorMessage = '해당 선거구에는 이미 등록된 사용자가 있습니다. 다른 선거구를 선택해주세요.';
        } else if (e.message.includes('network') || e.message.includes('연결')) {
          errorMessage = '인터넷 연결을 확인하고 다시 시도해주세요.';
        } else if (e.message.includes('선거구')) {
          errorMessage = '선거구 설정 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.';
        } else {
          errorMessage = '저장 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.';
        }
      }
      
      setError(errorMessage);
      
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <Container 
        maxWidth="xl" 
        sx={{ 
          py: 4,
          maxWidth: {
            xs: '100%',
            sm: '100%', 
            md: '900px',
            lg: '1200px',
            xl: '1400px',
            xxl: '1800px', // 2K 화면
            xxxl: '2400px', // 4K 화면
          }
        }}
      >
          <LoadingSpinner message="프로필 로딩 중..." fullHeight={true} />
        </Container>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <Container
        maxWidth="xl"
        sx={{
          py: 4,
          maxWidth: {
            xs: '100%',
            sm: '100%',
            md: '900px',
            lg: '1200px',
            xl: '1400px',
            xxl: '1800px', // 2K 화면
            xxxl: '2400px', // 4K 화면
          }
        }}
      >
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <Box sx={{ mb: `${spacing.xl}px` }}>
            <Typography variant="h4" sx={{
              fontWeight: 'bold',
              mb: `${spacing.xs}px`,
              color: theme.palette.mode === 'dark' ? 'white' : 'black',
              display: 'flex',
              alignItems: 'center',
              gap: `${spacing.xs}px`
            }}>
              <Settings sx={{ color: theme.palette.mode === 'dark' ? 'white' : 'black' }} />
              프로필 수정
            </Typography>
            <Typography variant="body1" sx={{ color: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.6)' }}>
              프로필 정보를 바탕으로 맞춤형 원고가 생성됩니다.
            </Typography>
          </Box>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <Grid container spacing={3}>
          {/* 좌측 컬럼: 기본 정보 */}
          <Grid item xs={12} xxl={6} xxxl={6}>
            <Paper elevation={0} sx={{
              p: `${spacing.lg}px`,
              height: 'fit-content'
            }}>
              <Box component="form" onSubmit={handleProfileSubmit}>
                <Grid container spacing={3}>
              
              {/* 🔧 UserInfoForm 컴포넌트 사용 */}
              <UserInfoForm
                name={profile.name}
                status={profile.status}
                customTitle={profile.customTitle}
                savedCustomTitle={savedCustomTitle}
                position={profile.position}
                regionMetro={profile.regionMetro}
                regionLocal={profile.regionLocal}
                electoralDistrict={profile.electoralDistrict}
                onChange={handleUserInfoChange}
                onCustomTitleSave={handleCustomTitleSave}
                nameDisabled={true}
                disabled={saving}
                showTitle={true}
              />

              {/* 개인화 정보 섹션 (선택사항) */}
              <Grid item xs={12}>
                <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', mb: `${spacing.md}px`, mt: `${spacing.lg}px` }}>
                  <AutoAwesome sx={{ mr: `${spacing.xs}px`, color: 'colors.brand.primary' }} />
                  개인화 정보 (선택사항)
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: `${spacing.lg}px` }}>
                  더 개인화되고 진정성 있는 원고 생성을 위한 선택 정보입니다. 입력하지 않아도 서비스 이용에 문제없습니다.
                </Typography>
              </Grid>

              {/* 연령대 - 연대 */}
              <Grid item xs={12} sm={6} md={2}>
                <FormControl fullWidth>
                  <InputLabel>연령대</InputLabel>
                  <Select
                    name="ageDecade"
                    value={profile.ageDecade || ''}
                    label="연령대"
                    onChange={(e) => handleUserInfoChange('ageDecade', e.target.value)}
                    disabled={saving}
                  >
                    <MenuItem value="">선택 안함</MenuItem>
                    <MenuItem value="20대">20대</MenuItem>
                    <MenuItem value="30대">30대</MenuItem>
                    <MenuItem value="40대">40대</MenuItem>
                    <MenuItem value="50대">50대</MenuItem>
                    <MenuItem value="60대">60대</MenuItem>
                    <MenuItem value="70대 이상">70대 이상</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              {/* 연령대 - 세부 */}
              <Grid item xs={12} sm={6} md={2}>
                <FormControl fullWidth>
                  <InputLabel>세부 연령</InputLabel>
                  <Select
                    name="ageDetail"
                    value={profile.ageDetail || ''}
                    label="세부 연령"
                    onChange={(e) => handleUserInfoChange('ageDetail', e.target.value)}
                    disabled={saving || !profile.ageDecade}
                  >
                    <MenuItem value="">선택 안함</MenuItem>
                    <MenuItem value="초반">초반</MenuItem>
                    <MenuItem value="중반">중반</MenuItem>
                    <MenuItem value="후반">후반</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              {/* 성별 */}
              <Grid item xs={12} sm={6} md={4}>
                <FormControl fullWidth>
                  <InputLabel>성별</InputLabel>
                  <Select
                    name="gender"
                    value={profile.gender}
                    label="성별"
                    onChange={(e) => handleUserInfoChange('gender', e.target.value)}
                    disabled={saving}
                  >
                    <MenuItem value="">선택 안함</MenuItem>
                    <MenuItem value="남성">남성</MenuItem>
                    <MenuItem value="여성">여성</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              {/* 가족 상황 */}
              <Grid item xs={12} sm={6} md={4}>
                <FormControl fullWidth>
                  <InputLabel>가족 상황</InputLabel>
                  <Select
                    name="familyStatus"
                    value={profile.familyStatus}
                    label="가족 상황"
                    onChange={(e) => handleUserInfoChange('familyStatus', e.target.value)}
                    disabled={saving}
                  >
                    <MenuItem value="">선택 안함</MenuItem>
                    <MenuItem value="미혼">미혼</MenuItem>
                    <MenuItem value="기혼(자녀 있음)">기혼(자녀 있음)</MenuItem>
                    <MenuItem value="기혼(자녀 없음)">기혼(자녀 없음)</MenuItem>
                    <MenuItem value="한부모">한부모</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              {/* 배경 경력 */}
              <Grid item xs={12} sm={6} md={4}>
                <FormControl fullWidth>
                  <InputLabel>주요 배경</InputLabel>
                  <Select
                    name="backgroundCareer"
                    value={profile.backgroundCareer}
                    label="주요 배경"
                    onChange={(e) => handleUserInfoChange('backgroundCareer', e.target.value)}
                    disabled={saving}
                  >
                    <MenuItem value="">선택 안함</MenuItem>
                    <MenuItem value="교육자">교육자</MenuItem>
                    <MenuItem value="사업가">사업가</MenuItem>
                    <MenuItem value="공무원">공무원</MenuItem>
                    <MenuItem value="시민운동가">시민운동가</MenuItem>
                    <MenuItem value="법조인">법조인</MenuItem>
                    <MenuItem value="의료인">의료인</MenuItem>
                    <MenuItem value="기타">기타</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              {/* 지역 연고성 */}
              <Grid item xs={12} sm={6} md={4}>
                <FormControl fullWidth>
                  <InputLabel>지역 연고</InputLabel>
                  <Select
                    name="localConnection"
                    value={profile.localConnection}
                    label="지역 연고"
                    onChange={(e) => handleUserInfoChange('localConnection', e.target.value)}
                    disabled={saving}
                  >
                    <MenuItem value="">선택 안함</MenuItem>
                    <MenuItem value="토박이">토박이</MenuItem>
                    <MenuItem value="오래 거주">오래 거주 (10년 이상)</MenuItem>
                    <MenuItem value="이주민">이주민</MenuItem>
                    <MenuItem value="귀향">귀향</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              {/* 정치 경험 */}
              <Grid item xs={12} sm={6} md={4}>
                <FormControl fullWidth>
                  <InputLabel>정치 경험</InputLabel>
                  <Select
                    name="politicalExperience"
                    value={profile.politicalExperience}
                    label="정치 경험"
                    onChange={(e) => handleUserInfoChange('politicalExperience', e.target.value)}
                    disabled={saving}
                  >
                    <MenuItem value="">선택 안함</MenuItem>
                    <MenuItem value="초선">초선</MenuItem>
                    <MenuItem value="재선">재선</MenuItem>
                    <MenuItem value="3선 이상">3선 이상</MenuItem>
                    <MenuItem value="정치 신인">정치 신인</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              {/* X 프리미엄 구독 여부 */}
              <Grid item xs={12} sm={6} md={4}>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={profile.twitterPremium}
                      onChange={(e) => handleUserInfoChange('twitterPremium', e.target.checked)}
                      disabled={saving}
                      sx={{
                        color: 'colors.brand.primary',
                        '&.Mui-checked': {
                          color: 'colors.brand.primary'
                        }
                      }}
                    />
                  }
                  label="X 프리미엄 구독"
                  sx={{ mt: `${spacing.md}px` }}
                />
              </Grid>

              {/* 소속 위원회 */}
              <Grid item xs={12}>
                <Box sx={{ mb: `${spacing.lg}px` }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: `${spacing.md}px` }}>
                    <Typography variant="h6" sx={{ 
                      color: theme.palette.mode === 'dark' ? '#e1bee7' : 'colors.brand.primary', 
                      fontWeight: 600 
                    }}>
                      🏛️ 소속 위원회
                    </Typography>
                    <Tooltip title="위원회 추가">
                      <IconButton 
                        size="small" 
                        onClick={() => {
                          const newCommittees = [...profile.committees, ''];
                          handleUserInfoChange('committees', newCommittees);
                        }}
                        disabled={saving || profile.committees.length >= 5}
                        sx={{ 
                          width: 24,
                          height: 24,
                          backgroundColor: colors.brand.primary,
                          color: 'white',
                          border: '1px solid',
                          borderColor: 'colors.brand.primary',
                          '&:hover': { 
                            backgroundColor: colors.brand.primaryHover,
                            borderColor: 'colors.brand.primaryHover'
                          },
                          '&:disabled': {
                            backgroundColor: 'grey.50',
                            borderColor: 'grey.200',
                            color: 'grey.400'
                          }
                        }}
                      >
                        <Add sx={{ fontSize: 14 }} />
                      </IconButton>
                    </Tooltip>
                  </Box>

                  <Stack spacing={2}>
                    {profile.committees.map((committee, index) => (
                      <Paper key={index} elevation={0} sx={{
                        p: `${spacing.md}px`
                      }}>
                        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: `${spacing.md}px` }}>
                          <Box sx={{ flex: 1 }}>
                            <FormControl fullWidth>
                              <InputLabel>위원회 선택</InputLabel>
                              <Select
                                value={committee}
                                label="위원회 선택"
                                onChange={(e) => {
                                  const newCommittees = [...profile.committees];
                                  newCommittees[index] = e.target.value;
                                  handleUserInfoChange('committees', newCommittees);
                                }}
                                disabled={saving}
                              >
                                <MenuItem value="">선택 안함</MenuItem>
                                <MenuItem value="교육위원회">교육위원회</MenuItem>
                                <MenuItem value="보건복지위원회">보건복지위원회</MenuItem>
                                <MenuItem value="국토교통위원회">국토교통위원회</MenuItem>
                                <MenuItem value="기획재정위원회">기획재정위원회</MenuItem>
                                <MenuItem value="행정안전위원회">행정안전위원회</MenuItem>
                                <MenuItem value="문화체육관광위원회">문화체육관광위원회</MenuItem>
                                <MenuItem value="농림축산식품해양수산위원회">농림축산식품해양수산위원회</MenuItem>
                                <MenuItem value="산업통상자원중소벤처기업위원회">산업통상자원중소벤처기업위원회</MenuItem>
                                <MenuItem value="환경노동위원회">환경노동위원회</MenuItem>
                                <MenuItem value="정무위원회">정무위원회</MenuItem>
                                <MenuItem value="법제사법위원회">법제사법위원회</MenuItem>
                                <MenuItem value="국방위원회">국방위원회</MenuItem>
                                <MenuItem value="외교통일위원회">외교통일위원회</MenuItem>
                                <MenuItem value="정보위원회">정보위원회</MenuItem>
                                <MenuItem value="여성가족위원회">여성가족위원회</MenuItem>
                                <MenuItem value="과학기술정보방송통신위원회">과학기술정보방송통신위원회</MenuItem>
                                <MenuItem value="도시계획위원회">도시계획위원회</MenuItem>
                                <MenuItem value="경제위원회">경제위원회</MenuItem>
                                <MenuItem value="복지위원회">복지위원회</MenuItem>
                                <MenuItem value="기타">기타 (직접 입력)</MenuItem>
                              </Select>
                            </FormControl>

                            {/* 기타 선택 시 직접 입력 */}
                            {committee === '기타' && (
                              <TextField
                                fullWidth
                                label="위원회명 직접 입력"
                                value={profile.customCommittees?.[index] || ''}
                                onChange={(e) => {
                                  const newCustomCommittees = [...(profile.customCommittees || [])];
                                  newCustomCommittees[index] = e.target.value;
                                  handleUserInfoChange('customCommittees', newCustomCommittees);
                                }}
                                disabled={saving}
                                placeholder="예: 특별위원회, 소위원회명 등"
                                sx={{ mt: `${spacing.xs}px` }}
                              />
                            )}
                          </Box>

                          <IconButton
                            size="small"
                            onClick={() => {
                              const newCommittees = profile.committees.filter((_, i) => i !== index);
                              handleUserInfoChange('committees', newCommittees.length ? newCommittees : ['']);
                            }}
                            disabled={saving}
                            sx={{ 
                              color: 'error.main',
                              '&:hover': { bgcolor: 'error.50' }
                            }}
                          >
                            <Remove />
                          </IconButton>
                        </Box>
                      </Paper>
                    ))}
                  </Stack>
                </Box>
              </Grid>

              {/* 저장 버튼 */}
              <Grid item xs={12}>
                <LoadingButton
                  type="submit"
                  fullWidth
                  variant="contained"
                  loading={saving}
                  loadingText="저장 중..."
                  sx={{
                    mt: `${spacing.md}px`,
                    py: 1.5,
                    bgcolor: colors.brand.primary,
                    color: '#fff',
                    fontWeight: 600,
                    '&:hover': {
                      bgcolor: colors.brand.primaryHover
                    }
                  }}
                >
                  프로필 저장
                </LoadingButton>
              </Grid>

              {/* 에러 메시지 */}
              {error && (
                <Grid item xs={12}>
                  <Alert severity="error">{error}</Alert>
                </Grid>
              )}

                </Grid>
              </Box>
            </Paper>
          </Grid>

          {/* 우측 컬럼: Bio 엔트리들 */}
          <Grid item xs={12} xxl={6} xxxl={6}>
            <Paper elevation={0} sx={{
              p: `${spacing.lg}px`,
              height: 'fit-content'
            }}>
              <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', mb: `${spacing.md}px` }}>
                <AutoAwesome sx={{ mr: `${spacing.xs}px`, color: 'colors.brand.primary' }} />
                자기소개 및 추가 정보
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: `${spacing.lg}px` }}>
                다양한 유형의 정보를 추가하여 더 정확한 개인화 원고를 생성하세요.
              </Typography>

              {/* 1. 자기소개 섹션 */}
              <Box sx={{ mb: `${spacing.xl}px` }} data-bio-section="personal">
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: `${spacing.md}px` }}>
                  <Typography variant="h6" sx={{
                    color: theme.palette.mode === 'dark' ? '#81d4fa' : 'colors.brand.primaryHover',
                    fontWeight: 600
                  }}>
                    👤 자기소개
                  </Typography>
                  <Tooltip title="자기소개 항목 추가">
                    <IconButton 
                      size="small" 
                      onClick={() => addBioEntry('PERSONAL')}
                      disabled={saving || bioEntries.length >= VALIDATION_RULES.maxEntries}
                      sx={{ 
                        width: 24,
                        height: 24,
                        backgroundColor: colors.brand.primary,
                        color: 'white',
                        border: '1px solid',
                        borderColor: 'colors.brand.primary',
                        '&:hover': { 
                          backgroundColor: colors.brand.primaryHover,
                          borderColor: 'colors.brand.primaryHover'
                        },
                        '&:disabled': {
                          backgroundColor: 'grey.50',
                          borderColor: 'grey.200',
                          color: 'grey.400'
                        }
                      }}
                    >
                      <Add fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
                
                <Stack spacing={2}>
                  {getEntriesByCategory('PERSONAL').map((entry) => {
                    const index = bioEntries.findIndex(e => e.id === entry.id);
                    const typeConfig = Object.values(BIO_ENTRY_TYPES).find(t => t.id === entry.type) || BIO_ENTRY_TYPES.SELF_INTRODUCTION;
                    const isRequired = entry.type === 'self_introduction';

                    return (
                      <Paper key={entry.id} elevation={0} sx={{
                        p: `${spacing.md}px`
                      }}>
                        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: `${spacing.md}px` }}>
                          <Box sx={{ flex: 1 }}>
                            <TextField
                              required={isRequired}
                              fullWidth
                              multiline
                              rows={isRequired ? 4 : 5}
                              label={isRequired ? '자기소개 *필수' : '내용'}
                              value={entry.content}
                              onChange={(e) => handleBioEntryChange(index, 'content', e.target.value)}
                              disabled={saving}
                              placeholder={isRequired ? '본인의 정치 철학, 가치관, 지역에 대한 애정 등을 자유롭게 작성해주세요.' : '연설문, 기고문, 인터뷰 등을 자유롭게 올려 주세요.'}
                              inputProps={{ maxLength: typeConfig.maxLength }}
                              helperText={`${entry.content?.length || 0}/${typeConfig.maxLength}자`}
                              FormHelperTextProps={{ sx: { color: 'black' } }}
                            />
                          </Box>
                          
                          {!isRequired && (
                            <Tooltip title="이 항목 삭제">
                              <IconButton
                                size="small"
                                onClick={() => removeBioEntry(index)}
                                disabled={saving}
                                sx={{
                                  mt: `${spacing.xs}px`,
                                  width: 24,
                                  height: 24,
                                  backgroundColor: colors.brand.primary,
                                  color: 'white',
                                  border: '1px solid',
                                  borderColor: colors.brand.primary,
                                  '&:hover': {
                                    backgroundColor: colors.brand.primaryHover,
                                    borderColor: colors.brand.primaryHover
                                  },
                                  '&:disabled': {
                                    backgroundColor: 'grey.50',
                                    borderColor: 'grey.200',
                                    color: 'grey.400'
                                  }
                                }}
                              >
                                <Remove />
                              </IconButton>
                            </Tooltip>
                          )}
                        </Box>
                      </Paper>
                    );
                  })}
                </Stack>
              </Box>

              {/* 2. 추가 정보 섹션 (카드형 배치) */}
              <Box sx={{ mb: `${spacing.xl}px` }}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: `${spacing.md}px` }}>
                  <Typography variant="h6" sx={{ 
                    color: theme.palette.mode === 'dark' ? '#e1bee7' : 'colors.brand.primary', 
                    fontWeight: 600 
                  }}>
                    📋 추가 정보
                  </Typography>
                  <Tooltip title="추가 정보 항목 추가">
                    <IconButton 
                      size="small" 
                      onClick={() => addBioEntry('PERFORMANCE')}
                      disabled={saving || bioEntries.length >= VALIDATION_RULES.maxEntries}
                      sx={{ 
                        width: 24,
                        height: 24,
                        backgroundColor: colors.brand.primary,
                        color: 'white',
                        border: '1px solid',
                        borderColor: 'colors.brand.primary',
                        '&:hover': { 
                          backgroundColor: colors.brand.primaryHover,
                          borderColor: 'colors.brand.primaryHover'
                        },
                        '&:disabled': {
                          backgroundColor: 'grey.50',
                          borderColor: 'grey.200',
                          color: 'grey.400'
                        }
                      }}
                    >
                      <Add fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
                
                <Grid container spacing={2}>
                  {getEntriesByCategory('PERFORMANCE').map((entry) => {
                    const index = bioEntries.findIndex(e => e.id === entry.id);
                    const typeConfig = Object.values(BIO_ENTRY_TYPES).find(t => t.id === entry.type) || BIO_ENTRY_TYPES.POLICY;

                    return (
                      <Grid item xs={12} sm={6} md={4} key={entry.id}>
                        <Card elevation={0} sx={{
                          height: '100%',
                          display: 'flex',
                          flexDirection: 'column'
                        }}>
                          <CardContent sx={{ flex: 1 }}>
                            <Box sx={{ mb: `${spacing.md}px` }}>
                              <Chip
                                label={typeConfig.name}
                                size="small"
                                sx={{
                                  bgcolor: typeConfig.color,
                                  color: 'white',
                                  fontWeight: 600
                                }}
                              />
                            </Box>

                            <FormControl fullWidth sx={{ mb: `${spacing.md}px` }}>
                              <InputLabel>유형 선택</InputLabel>
                              <Select
                                value={entry.type}
                                label="유형 선택"
                                onChange={(e) => handleBioEntryChange(index, 'type', e.target.value)}
                                disabled={saving}
                                size="small"
                              >
                                {BIO_CATEGORIES.PERFORMANCE.types.map((type) => (
                                  <MenuItem key={type.id} value={type.id}>
                                    {type.name}
                                  </MenuItem>
                                ))}
                              </Select>
                            </FormControl>
                            
                            <TextField
                              fullWidth
                              multiline
                              rows={4}
                              label="내용"
                              value={entry.content}
                              onChange={(e) => handleBioEntryChange(index, 'content', e.target.value)}
                              disabled={saving}
                              placeholder={typeConfig.placeholder}
                              inputProps={{ maxLength: typeConfig.maxLength }}
                              size="small"
                            />
                          </CardContent>

                          <CardActions sx={{ justifyContent: 'space-between', px: `${spacing.md}px`, pb: `${spacing.md}px` }}>
                            <Typography variant="caption" color="text.secondary">
                              {entry.content?.length || 0}/{typeConfig.maxLength}자
                            </Typography>
                            <Tooltip title="이 항목 삭제">
                              <IconButton
                                size="small"
                                onClick={() => removeBioEntry(index)}
                                disabled={saving}
                                sx={{ 
                                  width: 24,
                                  height: 24,
                                  backgroundColor: colors.brand.primary,
                                  color: 'white',
                                  border: '1px solid',
                                  borderColor: colors.brand.primary,
                                  '&:hover': {
                                    backgroundColor: colors.brand.primaryHover,
                                    borderColor: colors.brand.primaryHover
                                  },
                                  '&:disabled': {
                                    backgroundColor: 'grey.50',
                                    borderColor: 'grey.200',
                                    color: 'grey.400'
                                  }
                                }}
                              >
                                <Remove />
                              </IconButton>
                            </Tooltip>
                          </CardActions>
                        </Card>
                      </Grid>
                    );
                  })}
                </Grid>
              </Box>

              {bioEntries.length >= VALIDATION_RULES.maxEntries && (
                <Alert severity="info" sx={{ mb: `${spacing.md}px` }}>
                  최대 {VALIDATION_RULES.maxEntries}개의 엔트리까지 추가할 수 있습니다.
                </Alert>
              )}

              {/* 프로필 저장 버튼 */}
              <LoadingButton
                fullWidth
                variant="contained"
                onClick={handleBioSubmit}
                loading={saving}
                disabled={saving}
                startIcon={<Save />}
                sx={{
                  mt: `${spacing.md}px`,
                  py: 1.5,
                  bgcolor: colors.brand.primary,
                  color: '#fff',
                  fontWeight: 600,
                  '&:hover': {
                    bgcolor: colors.brand.primaryHover
                  }
                }}
              >
                자기소개 및 추가 정보 저장
              </LoadingButton>
            </Paper>
          </Grid>
        </Grid>
        </motion.div>

        {/* 회원탈퇴 버튼 (최하단, 카드 폭과 동일) */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
        >
          <Box sx={{ mt: `${spacing.xl}px` }}>
          <Button
            onClick={() => setDeleteDialogOpen(true)}
            variant="contained"
            startIcon={<DeleteForever />}
            fullWidth
            sx={{
              bgcolor: '#d22730',
              color: 'white',
              '&:hover': {
                bgcolor: '#b71c1c'
              }
            }}
          >
            회원탈퇴
          </Button>
        </Box>
        </motion.div>

        {/* 알림 스낵바 */}
        <NotificationSnackbar
          open={notification.open}
          onClose={hideNotification}
          message={notification.message}
          severity={notification.severity}
          autoHideDuration={6000}
        />

        {/* 회원탈퇴 확인 다이얼로그 */}
        <Dialog 
          open={deleteDialogOpen} 
          onClose={handleCloseDeleteDialog}
          maxWidth="sm" 
          fullWidth
        >
          <DialogTitle>
            <Box display="flex" alignItems="center" gap={`${spacing.xs}px`}>
              <Warning color="error" />
              <Typography variant="h6" component="span">
                회원탈퇴 확인
              </Typography>
            </Box>
          </DialogTitle>

          <DialogContent>
            <Alert severity="error" sx={{ mb: `${spacing.lg}px` }}>
              <Typography variant="body1" sx={{ fontWeight: 600, mb: `${spacing.xs}px` }}>
                ⚠️ 회원탈퇴 시 다음 데이터가 영구적으로 삭제됩니다:
              </Typography>
              <Typography component="div">
                • 모든 게시물 및 댓글<br/>
                • 프로필 정보 및 Bio 데이터<br/>
                • 선거구 점유 정보<br/>
                • 계정 정보 (복구 불가능)
              </Typography>
            </Alert>

            <Typography variant="body1" sx={{ mb: `${spacing.md}px` }}>
              정말로 회원탈퇴를 진행하시겠습니까?
            </Typography>

            <Typography variant="body2" color="text.secondary" sx={{ mb: `${spacing.md}px` }}>
              탈퇴를 확인하려면 아래에 <strong>"회원탈퇴"</strong>를 정확히 입력해주세요.
            </Typography>
            
            <TextField
              fullWidth
              label="확인 문구 입력"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              placeholder="회원탈퇴"
              disabled={deleting}
              error={deleteConfirmText !== '' && deleteConfirmText !== '회원탈퇴'}
              helperText={
                deleteConfirmText !== '' && deleteConfirmText !== '회원탈퇴' 
                  ? '정확히 "회원탈퇴"를 입력해주세요.' 
                  : ''
              }
              FormHelperTextProps={{ sx: { color: 'black' } }}
            />
          </DialogContent>
          
          <DialogActions>
            <Button 
              onClick={handleCloseDeleteDialog} 
              disabled={deleting}
            >
              취소
            </Button>
            <LoadingButton
              onClick={handleDeleteAccount}
              color="error"
              variant="contained"
              disabled={deleteConfirmText !== '회원탈퇴'}
              loading={deleting}
              loadingText="탈퇴 처리 중..."
              startIcon={<DeleteForever />}
            >
              회원탈퇴
            </LoadingButton>
          </DialogActions>
        </Dialog>

        {/* 온보딩 Bio 가이드 모달 */}
        <ProfileBioGuideModal
          open={bioGuideOpen}
          onClose={() => setBioGuideOpen(false)}
          onStartWriting={() => {
            setBioGuideOpen(false);
            // 모달 닫힌 후 글로우 2회 반복하고 텍스트박스로 포커스 이동
            setTimeout(() => {
              const bioCard = document.querySelector('[data-bio-section="personal"]');
              if (bioCard) {
                let glowCount = 0;
                const maxGlows = 2;

                const glowCycle = () => {
                  if (glowCount >= maxGlows) {
                    // 모든 글로우 완료 후 텍스트박스 포커스
                    const bioTextarea = document.querySelector('textarea[placeholder*="자기소개"]');
                    if (bioTextarea) {
                      bioTextarea.focus();
                      bioTextarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                    return;
                  }

                  // 글로우 효과 적용 (시안색, 부드러운 강도)
                  bioCard.style.position = 'relative';
                  bioCard.style.zIndex = '100';
                  bioCard.style.boxShadow = '0 0 15px 3px rgba(0, 188, 212, 0.5), 0 0 25px 8px rgba(0, 188, 212, 0.2)';
                  bioCard.style.borderRadius = '12px';
                  bioCard.style.transition = 'all 0.3s ease';
                  bioCard.style.transform = 'scale(1.01)';

                  // 0.3초 후 글로우 제거
                  setTimeout(() => {
                    bioCard.style.position = '';
                    bioCard.style.zIndex = '';
                    bioCard.style.boxShadow = '';
                    bioCard.style.transform = '';

                    glowCount++;

                    // 0.2초 후 다음 글로우 또는 완료
                    setTimeout(glowCycle, 200);
                  }, 300);
                };

                // 첫 번째 글로우 시작
                glowCycle();
              } else {
                // 카드를 찾지 못한 경우 바로 텍스트박스 포커스
                const bioTextarea = document.querySelector('textarea[placeholder*="자기소개"]');
                if (bioTextarea) {
                  bioTextarea.focus();
                  bioTextarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
              }
            }, 300);
          }}
          userName={user?.displayName || user?.name}
        />

        {/* 축하 모달 */}
        <CongratulationsModal
          open={congratulationsOpen}
          onClose={() => setCongratulationsOpen(false)}
          userName={user?.displayName || user?.name}
          bioContent={profile.bio}
        />

      </Container>
    </DashboardLayout>
  );
}