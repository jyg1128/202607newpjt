const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
const IS_STATIC_HOST = location.hostname.endsWith('github.io');
const state = { image: null, expenses: JSON.parse(localStorage.getItem('clearcost-expenses') || '[]') };
const form = $('#expenseForm');
const fileInput = $('#fileInput');
const dropzone = $('#dropzone');
const keyModal = $('#keyModal');
const keyButton = $('#apiKeyBtn');

async function readJson(response) {
  const type = response.headers.get('content-type') || '';
  if (!type.includes('application/json')) throw new Error('API 서버가 JSON 응답을 반환하지 않았습니다.');
  return response.json();
}

async function refreshKeyStatus() {
  if (IS_STATIC_HOST) return;
  try {
    const response = await fetch('/api/config/status');
    if (!response.ok) return;
    const data = await readJson(response);
    keyButton.classList.toggle('connected', data.connected);
    keyButton.lastChild.textContent = data.connected ? ' API 연결됨' : ' API 키 연결';
  } catch (_) {}
}

if (IS_STATIC_HOST) {
  keyButton.classList.add('hidden');
  $('#staticNotice').classList.remove('hidden');
  $('#recognizeBtn').textContent = 'AI 인식은 로컬 서버에서 사용 가능';
} else {
  refreshKeyStatus();
}

keyButton.addEventListener('click', () => {
  keyModal.classList.remove('hidden');
  setTimeout(() => $('#apiKeyInput').focus(), 50);
});
$('#closeKeyModal').addEventListener('click', () => keyModal.classList.add('hidden'));
keyModal.addEventListener('click', (event) => { if (event.target === keyModal) keyModal.classList.add('hidden'); });
$('#keyForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const input = $('#apiKeyInput');
  const message = $('#keyMessage');
  const button = event.submitter;
  button.disabled = true;
  message.textContent = '연결을 확인하고 있어요...';
  try {
    const response = await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ apiKey: input.value }) });
    const data = await readJson(response);
    if (!response.ok) throw new Error(data.error || '연결하지 못했습니다.');
    input.value = '';
    message.style.color = 'var(--green)';
    message.textContent = '연결되었습니다.';
    await refreshKeyStatus();
    setTimeout(() => keyModal.classList.add('hidden'), 600);
  } catch (error) {
    message.style.color = 'var(--danger)';
    message.textContent = error.message;
  } finally { button.disabled = false; }
});

function setView(id) {
  $$('.view').forEach((view) => view.classList.toggle('active', view.id === id));
  $$('.nav').forEach((item) => item.classList.toggle('active', item.dataset.view === id));
  if (id !== 'register') renderLists();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
$$('[data-view]').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));

function loadImage(file) {
  if (!file || !file.type.startsWith('image/')) return alert('이미지 파일을 선택해주세요.');
  if (file.size > 10 * 1024 * 1024) return alert('10MB 이하 이미지를 선택해주세요.');
  const reader = new FileReader();
  reader.onload = () => {
    state.image = reader.result;
    $('#preview').src = state.image;
    $('#preview').style.display = 'block';
    $('#dropPrompt').classList.add('hidden');
    $('#recognizeBtn').disabled = IS_STATIC_HOST;
    $('#changeBtn').classList.remove('hidden');
    $('#imageBadge').textContent = '업로드 완료';
  };
  reader.readAsDataURL(file);
}
fileInput.addEventListener('change', (event) => loadImage(event.target.files[0]));
['dragenter', 'dragover'].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.add('drag'); }));
['dragleave', 'drop'].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.remove('drag'); }));
dropzone.addEventListener('drop', (event) => loadImage(event.dataTransfer.files[0]));
$('#changeBtn').addEventListener('click', () => fileInput.click());

$('#recognizeBtn').addEventListener('click', async () => {
  if (IS_STATIC_HOST) return;
  const button = $('#recognizeBtn');
  button.disabled = true;
  button.textContent = '원본 해상도로 정밀 분석 중...';
  $('#resultBadge').textContent = '인식 중';
  try {
    const response = await fetch('/api/recognize-receipt', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ imageBase64: state.image }) });
    const result = await readJson(response);
    if (!response.ok) throw new Error(result.error || 'AI 인식에 실패했습니다.');
    const values = result.extracted || {};
    Object.entries(values).forEach(([key, value]) => { if (form.elements[key] && value !== null) form.elements[key].value = value; });
    if (!values.amount && values.taxableAmount !== null && values.vat !== null) form.elements.amount.value = Number(values.taxableAmount) + Number(values.vat);
    Object.entries(result.confidence || {}).forEach(([key, value]) => {
      const element = document.querySelector(`[data-confidence="${key}"]`);
      if (element) { element.className = `confidence ${value}`; element.textContent = { high: '높음', medium: '보통', low: '낮음' }[value] || '확인 필요'; }
    });
    $('#warning').textContent = (result.warnings || []).join(' · ') || '모든 필드를 높은 신뢰도로 인식했습니다.';
    $('#emptyState').classList.add('hidden');
    form.classList.remove('hidden');
    $('#resultBadge').textContent = 'AI 인식 완료';
    button.textContent = '다시 인식하기';
  } catch (error) {
    $('#resultBadge').textContent = '인식 실패';
    button.textContent = '다시 시도하기';
    alert(error.message);
  } finally { button.disabled = false; }
});

form.addEventListener('submit', (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const data = Object.fromEntries(new FormData(form));
  data.amount = Number(data.amount);
  data.vat = Number(data.vat || 0);
  data.settlementIncluded = form.elements.settlementIncluded.checked;
  data.id = `EXP-${Date.now()}`;
  data.image = state.image;
  state.expenses.unshift(data);
  localStorage.setItem('clearcost-expenses', JSON.stringify(state.expenses));
  $('#toast').classList.add('show');
  setTimeout(() => $('#toast').classList.remove('show'), 2800);
  setTimeout(() => setView('settlement'), 650);
});

function renderLists() {
  const included = state.expenses.filter((item) => item.settlementIncluded);
  $('#totalAmount').textContent = `${included.reduce((sum, item) => sum + item.amount, 0).toLocaleString('ko-KR')}원`;
  $('#settlementRows').innerHTML = included.map((item) => `<tr><td>${item.paidDate}</td><td><strong>${item.project}</strong><br>${item.artist}</td><td>${item.merchant}</td><td>${item.category}</td><td>${item.purpose}</td><td class="right"><strong>${item.amount.toLocaleString('ko-KR')}원</strong></td><td><span class="status">정산 반영 가능</span></td></tr>`).join('');
  $('#settlementEmpty').classList.toggle('hidden', included.length > 0);
  $('#archiveGrid').innerHTML = state.expenses.map((item) => `<article class="archive-card"><img src="${item.image}" alt="영수증"><div class="archive-info"><strong>${item.merchant}</strong><span>${item.paidDate} · ${item.amount.toLocaleString('ko-KR')}원 · ${item.artist}</span></div></article>`).join('');
  $('#archiveEmpty').classList.toggle('hidden', state.expenses.length > 0);
}
renderLists();
