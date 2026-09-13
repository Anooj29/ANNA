/* Interface copy only. Clinical observations remain in their recorded language. */
const portalStrings = {
  en: {
    language: 'Language', idHelp: 'Issued during admission at the reception desk.',
    portalTitle: 'Patient Care Portal', portalSubtitle: 'Your ANNA checkup records and care history',
    patientId: 'Patient ID', accessPin: '6-digit access PIN', viewRecords: 'View my health records',
    signOut: 'Sign out', welcome: name => `Welcome, ${name}`,
    welcomeDescription: 'Review recent ANNA visits, measurements and prescribed medicines.',
    careNoteTitle: 'Care team note:',
    careNote: 'ANNA records observations during rounds. It does not diagnose illness. Your care team reviews the readings.',
    latestReadings: '🩺 My latest health readings', healthProgress: '📊 My health progress',
    visitHistory: '💬 ANNA visit history', medications: '💊 My prescribed medicines'
  },
  hi: {
    language: 'भाषा', idHelp: 'प्रवेश के समय स्वागत कक्ष से दिया जाता है।',
    portalTitle: 'रोगी देखभाल पोर्टल', portalSubtitle: 'आपके ANNA जाँच रिकॉर्ड और देखभाल का इतिहास',
    patientId: 'रोगी आईडी', accessPin: '6 अंकों का प्रवेश पिन', viewRecords: 'मेरे स्वास्थ्य रिकॉर्ड देखें',
    signOut: 'साइन आउट', welcome: name => `स्वागत है, ${name}`,
    welcomeDescription: 'हाल की ANNA मुलाकातें, माप और निर्धारित दवाएँ देखें।',
    careNoteTitle: 'देखभाल टीम का नोट:',
    careNote: 'ANNA देखभाल के दौरान जानकारी दर्ज करता है। यह रोग का निदान नहीं करता। आपकी देखभाल टीम मापों की समीक्षा करती है।',
    latestReadings: '🩺 मेरे नवीनतम स्वास्थ्य माप', healthProgress: '📊 स्वास्थ्य प्रगति',
    visitHistory: '💬 ANNA मुलाकातों का इतिहास', medications: '💊 मेरी निर्धारित दवाएँ'
  },
  mr: {
    language: 'भाषा', idHelp: 'रुग्ण दाखल होताना स्वागत कक्षात दिला जातो.',
    portalTitle: 'रुग्ण सेवा पोर्टल', portalSubtitle: 'तुमचे ANNA तपासणी नोंदी आणि उपचार इतिहास',
    patientId: 'रुग्ण आयडी', accessPin: '६ अंकी प्रवेश पिन', viewRecords: 'माझ्या आरोग्य नोंदी पाहा',
    signOut: 'साइन आउट', welcome: name => `स्वागत आहे, ${name}`,
    welcomeDescription: 'अलीकडील ANNA भेटी, मोजमापे आणि लिहून दिलेली औषधे पाहा.',
    careNoteTitle: 'उपचार पथकाची नोंद:',
    careNote: 'ANNA भेटीदरम्यान निरीक्षणे नोंदवते. ते रोगनिदान करत नाही. तुमचे उपचार पथक मोजमापे तपासते.',
    latestReadings: '🩺 माझी नवीनतम आरोग्य मोजमापे', healthProgress: '📊 आरोग्यातील बदल',
    visitHistory: '💬 ANNA भेटींचा इतिहास', medications: '💊 माझी लिहून दिलेली औषधे'
  }
};
const portalLanguage = document.getElementById('portal-language');
window.portalTranslate = (key, ...values) => {
  const translation = portalStrings[portalLanguage.value]?.[key] ?? portalStrings.en[key] ?? key;
  return typeof translation === 'function' ? translation(...values) : translation;
};
function applyPortalLanguage() {
  document.documentElement.lang = portalLanguage.value;
  document.querySelectorAll('[data-i18n]').forEach(element => {
    element.textContent = window.portalTranslate(element.dataset.i18n);
  });
  if (window.portalPatientName) {
    document.getElementById('patient-welcome-heading').textContent = window.portalTranslate('welcome', window.portalPatientName);
  }
  localStorage.setItem('anna.portal.language', portalLanguage.value);
}
portalLanguage.value = localStorage.getItem('anna.portal.language') in portalStrings
  ? localStorage.getItem('anna.portal.language') : 'en';
portalLanguage.addEventListener('change', applyPortalLanguage);
applyPortalLanguage();
