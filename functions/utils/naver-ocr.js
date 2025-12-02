const axios = require('axios');
const { defineSecret } = require('firebase-functions/params');

// Firebase Functions Secrets로 정의
const NAVER_OCR_SECRET_KEY = defineSecret('NAVER_OCR_SECRET_KEY');
const NAVER_OCR_API_URL = defineSecret('NAVER_OCR_API_URL');

/**
 * 네이버 OCR API를 호출하여 이미지에서 텍스트를 추출합니다.
 * @param {string} imageUrl - 분석할 이미지의 URL 또는 Base64 데이터
 * @param {string} format - 이미지 형식 ('jpg', 'png', 'pdf' 등)
 * @param {number} templateId - 네이버 OCR 템플릿 ID (39477: 당적증명서, 39478: 당비납부내역서)
 * @returns {Promise<Object>} OCR 결과 객체
 */
async function extractTextFromImage(imageUrl, format = 'jpg', templateId) {
  try {
    const secretKey = NAVER_OCR_SECRET_KEY.value().trim();
    const apiUrl = NAVER_OCR_API_URL.value().trim();

    // 네이버 OCR API 요청 바디
    const requestBody = {
      version: 'V2',
      requestId: `ocr-${Date.now()}`,
      timestamp: Date.now(),
      images: [
        {
          format: format,
          name: 'party_certificate',
          // URL 또는 Base64 데이터
          ...(imageUrl.startsWith('http')
            ? { url: imageUrl }
            : { data: imageUrl.split(',')[1] || imageUrl })
        }
      ]
    };

    // Custom Template 사용 시 templateIds 추가
    if (templateId) {
      requestBody.templateIds = [templateId];
    }

    // 디버깅: 요청 내용 로그
    console.log('OCR API 요청:', {
      url: apiUrl,
      templateId: templateId,
      hasTemplateIds: !!requestBody.templateIds,
      imageFormat: requestBody.images[0].format,
      imageDataLength: requestBody.images[0].data ? requestBody.images[0].data.length : 0
    });

    // API 호출
    const response = await axios.post(apiUrl, requestBody, {
      headers: {
        'Content-Type': 'application/json',
        'X-OCR-SECRET': secretKey
      }
    });

    console.log('OCR API 성공:', {
      status: response.status,
      imageCount: response.data?.images?.length || 0
    });

    return {
      success: true,
      data: response.data,
      extractedText: parseOCRResult(response.data)
    };
  } catch (error) {
    console.error('네이버 OCR API 호출 실패:', error.response?.data || error.message);
    return {
      success: false,
      error: error.message,
      details: error.response?.data
    };
  }
}

/**
 * OCR 결과에서 텍스트를 추출하고 파싱합니다.
 * @param {Object} ocrData - 네이버 OCR API 응답 데이터
 * @returns {Object} 파싱된 텍스트 정보
 */
function parseOCRResult(ocrData) {
  if (!ocrData || !ocrData.images || ocrData.images.length === 0) {
    return { text: '', fields: [], structuredFields: {} };
  }

  const image = ocrData.images[0];
  let fullText = '';
  const fields = [];
  const structuredFields = {};

  // 모든 필드의 텍스트 추출
  if (image.fields) {
    image.fields.forEach(field => {
      const text = field.inferText || '';
      const fieldName = field.name || '';

      fullText += text + '\n';

      // 구조화된 필드로 저장 (Custom Template 사용 시)
      if (fieldName) {
        structuredFields[fieldName] = {
          text: text,
          confidence: field.inferConfidence
        };
      }

      fields.push({
        name: fieldName,
        text: text,
        confidence: field.inferConfidence,
        boundingBox: field.boundingPoly
      });
    });
  }

  return {
    text: fullText.trim(),
    fields: fields,
    structuredFields: structuredFields,
    inferResult: image.inferResult
  };
}

/**
 * 당적증명서에서 주요 정보를 추출합니다.
 * @param {Object} ocrResult - OCR 결과 (structuredFields 포함)
 * @returns {Object} 추출된 당적 정보
 */
function extractPartyInfo(ocrResult) {
  const structuredFields = ocrResult.structuredFields || {};
  const extractedText = ocrResult.text || '';

  const info = {
    isValid: false,
    name: null,
    joinDate: null,
    issueDate: null,
    confidence: {},
    rawText: extractedText
  };

  // 1. 구조화된 필드에서 먼저 추출 (Custom Template 사용 시)
  if (structuredFields.name) {
    info.name = structuredFields.name.text.trim();
    info.confidence.name = structuredFields.name.confidence;
  }

  if (structuredFields.joinDate) {
    info.joinDate = normalizeDate(structuredFields.joinDate.text);
    info.confidence.joinDate = structuredFields.joinDate.confidence;
  }

  if (structuredFields.issueDate) {
    info.issueDate = normalizeDate(structuredFields.issueDate.text);
    info.confidence.issueDate = structuredFields.issueDate.confidence;
  }

  // 2. 구조화된 필드가 없으면 정규식으로 Fallback
  if (!info.name) {
    // 더 관대한 성명 매칭 (성명, 이름, 성 명, 氏名 등)
    const nameMatch = extractedText.match(/(?:성\s*명|이\s*름|姓\s*名|氏\s*名|성명|이름)[\s:：]*([가-힣]{2,5})/);
    if (nameMatch) {
      info.name = nameMatch[1].replace(/\s/g, ''); // 공백 제거
      info.confidence.name = 0.5;
    }
  }

  if (!info.joinDate) {
    // 더 관대한 입당일 매칭 (입당일, 가입일, 입당연월일, 가입연월일 등)
    const joinDateMatch = extractedText.match(/(?:입\s*당\s*[일연월]*|가\s*입\s*[일연월]*)[\s:：]*(\d{4})[\s년.\-/]*(\d{1,2})[\s월.\-/]*(\d{1,2})[일\s]*/);
    if (joinDateMatch) {
      info.joinDate = `${joinDateMatch[1]}-${joinDateMatch[2].padStart(2, '0')}-${joinDateMatch[3].padStart(2, '0')}`;
      info.confidence.joinDate = 0.5;
    }
  }

  if (!info.issueDate) {
    // 더 관대한 발행일 매칭 (연도 있는 경우)
    let issueDateMatch = extractedText.match(/(?:발\s*[행급]\s*[일자]*)[\s:：]*(\d{4})[\s년.\-/]*(\d{1,2})[\s월.\-/]*(\d{1,2})[일\s]*/);
    if (issueDateMatch) {
      info.issueDate = `${issueDateMatch[1]}-${issueDateMatch[2].padStart(2, '0')}-${issueDateMatch[3].padStart(2, '0')}`;
      info.confidence.issueDate = 0.5;
    } else {
      // 연도 없는 경우 (예: "12월 02일") - 현재 연도 사용
      issueDateMatch = extractedText.match(/(\d{1,2})[\s월.\-/]+(\d{1,2})[일\s]*/);
      if (issueDateMatch) {
        const currentYear = new Date().getFullYear();
        info.issueDate = `${currentYear}-${issueDateMatch[1].padStart(2, '0')}-${issueDateMatch[2].padStart(2, '0')}`;
        info.confidence.issueDate = 0.3;
      }
    }
  }

  // 디버깅: 추출 결과 로그
  console.log('당적증명서 정보 추출 결과:', {
    name: info.name,
    joinDate: info.joinDate,
    issueDate: info.issueDate,
    isValid: info.isValid,
    textLength: extractedText.length,
    textSample: extractedText.substring(0, 200)
  });

  // 3. 유효성 검증: 필수 필드가 모두 있어야 함
  info.isValid = !!(info.name && info.joinDate && info.issueDate);

  return info;
}

/**
 * 날짜 문자열을 YYYY-MM-DD 형식으로 정규화합니다.
 * @param {string} dateStr - 날짜 문자열 (예: "2024년 1월 15일", "2024.01.15", "20240115")
 * @returns {string|null} 정규화된 날짜 (YYYY-MM-DD) 또는 null
 */
function normalizeDate(dateStr) {
  if (!dateStr) return null;

  // 공백 제거
  const cleaned = dateStr.replace(/\s+/g, '');

  // 패턴 1: YYYY년MM월DD일 or YYYY년M월D일
  let match = cleaned.match(/(\d{4})년(\d{1,2})월(\d{1,2})일?/);
  if (match) {
    return `${match[1]}-${match[2].padStart(2, '0')}-${match[3].padStart(2, '0')}`;
  }

  // 패턴 2: YYYY.MM.DD or YYYY-MM-DD or YYYY/MM/DD
  match = cleaned.match(/(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})/);
  if (match) {
    return `${match[1]}-${match[2].padStart(2, '0')}-${match[3].padStart(2, '0')}`;
  }

  // 패턴 3: YYYYMMDD
  match = cleaned.match(/^(\d{4})(\d{2})(\d{2})$/);
  if (match) {
    return `${match[1]}-${match[2]}-${match[3]}`;
  }

  return null;
}

/**
 * 당비 납부 내역서에서 정보를 추출합니다.
 * @param {Object} ocrResult - OCR 결과 (structuredFields 포함)
 * @returns {Object} 추출된 납부 정보
 */
function extractPaymentInfo(ocrResult) {
  const structuredFields = ocrResult.structuredFields || {};
  const extractedText = ocrResult.text || '';

  const info = {
    isValid: false,
    name: null,
    paymentMonth: null,
    issueDate: null,
    confidence: {},
    rawText: extractedText
  };

  // 1. 구조화된 필드에서 먼저 추출 (Custom Template 사용 시)
  if (structuredFields.name) {
    info.name = structuredFields.name.text.trim();
    info.confidence.name = structuredFields.name.confidence;
  }

  // 템플릿 필드명이 paymentMatch임 (paymentMonth가 아님)
  if (structuredFields.paymentMatch) {
    info.paymentMonth = normalizeYearMonth(structuredFields.paymentMatch.text);
    info.confidence.paymentMonth = structuredFields.paymentMatch.confidence;
  }

  if (structuredFields.issueDate) {
    info.issueDate = normalizeDate(structuredFields.issueDate.text);
    info.confidence.issueDate = structuredFields.issueDate.confidence;
  }

  // 2. 구조화된 필드가 없으면 정규식으로 Fallback
  if (!info.name) {
    // 더 관대한 성명 매칭
    const nameMatch = extractedText.match(/(?:성\s*명|납\s*부\s*자|입\s*금\s*자|성명|납부자|입금자)[\s:：]*([가-힣]{2,5})/);
    if (nameMatch) {
      info.name = nameMatch[1].replace(/\s/g, '');
      info.confidence.name = 0.5;
    }
  }

  if (!info.paymentMonth) {
    // 더 관대한 납입연월 매칭
    const paymentMatch = extractedText.match(/(?:납\s*[입부]\s*[연]*\s*월|납입연월|납부연월|납입월|납부월)[\s:：]*(\d{4})[\s년.\-/]*(\d{1,2})[월\s]*/);
    if (paymentMatch) {
      info.paymentMonth = `${paymentMatch[1]}-${paymentMatch[2].padStart(2, '0')}`;
      info.confidence.paymentMonth = 0.5;
    }
  }

  if (!info.issueDate) {
    // 더 관대한 발행일 매칭 (연도 있는 경우)
    let issueDateMatch = extractedText.match(/(?:발\s*[행급]\s*[일자]*)[\s:：]*(\d{4})[\s년.\-/]*(\d{1,2})[\s월.\-/]*(\d{1,2})[일\s]*/);
    if (issueDateMatch) {
      info.issueDate = `${issueDateMatch[1]}-${issueDateMatch[2].padStart(2, '0')}-${issueDateMatch[3].padStart(2, '0')}`;
      info.confidence.issueDate = 0.5;
    } else {
      // 연도 없는 경우 (예: "12월 02일") - 현재 연도 사용
      issueDateMatch = extractedText.match(/(\d{1,2})[\s월.\-/]+(\d{1,2})[일\s]*/);
      if (issueDateMatch) {
        const currentYear = new Date().getFullYear();
        info.issueDate = `${currentYear}-${issueDateMatch[1].padStart(2, '0')}-${issueDateMatch[2].padStart(2, '0')}`;
        info.confidence.issueDate = 0.3; // 연도 추론이므로 낮은 신뢰도
      }
    }
  }

  // 디버깅: 추출 결과 로그
  console.log('당비납부내역 정보 추출 결과:', {
    name: info.name,
    paymentMonth: info.paymentMonth,
    issueDate: info.issueDate,
    isValid: info.isValid,
    textLength: extractedText.length,
    textSample: extractedText.substring(0, 200)
  });

  // 3. 유효성 검증: 성명과 발행일만 필수 (납입연월은 선택사항)
  info.isValid = !!(info.name && info.issueDate);

  return info;
}

/**
 * 연월 문자열을 YYYY-MM 형식으로 정규화합니다.
 * @param {string} yearMonthStr - 연월 문자열 (예: "2024년 11월", "2024.11", "202411")
 * @returns {string|null} 정규화된 연월 (YYYY-MM) 또는 null
 */
function normalizeYearMonth(yearMonthStr) {
  if (!yearMonthStr) return null;

  // 공백 제거
  const cleaned = yearMonthStr.replace(/\s+/g, '');

  // 패턴 1: YYYY년MM월
  let match = cleaned.match(/(\d{4})년(\d{1,2})월?/);
  if (match) {
    return `${match[1]}-${match[2].padStart(2, '0')}`;
  }

  // 패턴 2: YYYY.MM or YYYY-MM or YYYY/MM
  match = cleaned.match(/(\d{4})[.\-/](\d{1,2})/);
  if (match) {
    return `${match[1]}-${match[2].padStart(2, '0')}`;
  }

  // 패턴 3: YYYYMM
  match = cleaned.match(/^(\d{4})(\d{2})$/);
  if (match) {
    return `${match[1]}-${match[2]}`;
  }

  return null;
}

module.exports = {
  extractTextFromImage,
  parseOCRResult,
  extractPartyInfo,
  extractPaymentInfo,
  normalizeDate,
  normalizeYearMonth,
  NAVER_OCR_SECRET_KEY,
  NAVER_OCR_API_URL
};
