let token = sessionStorage.getItem('tc_token') || '';
let user = null;
let registering = false;
let bookingFilter = 'upcoming';
let calendarOffset = new Date().getDay() === 0 ? 1 : 0;
let calendarEvents = [];
let installPrompt = null;
let moduleOptions = [];
let searchTimer = null;
let tutorRequestId = 0;

const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));

function msg(text, error = false) {
  const notice = $('notice');
  notice.textContent = text;
  notice.className = error ? 'error' : '';
  notice.style.display = 'block';
  clearTimeout(notice.hideTimer);
  notice.hideTimer = setTimeout(() => { notice.style.display = 'none'; }, 4500);
}

async function api(path, method = 'GET', data) {
  const response = await fetch('/api' + path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: 'Bearer ' + token } : {})
    },
    body: data === undefined ? undefined : JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}

function toggleSidebar(force) {
  const open = typeof force === 'boolean' ? force : !$('sidebar').classList.contains('open');
  $('sidebar').classList.toggle('open', open);
  $('mobileOverlay').classList.toggle('visible', open);
  $('menuToggle').setAttribute('aria-expanded', String(open));
}

function show(page) {
  document.querySelectorAll('.view').forEach(section => section.classList.add('hidden'));
  const section = $(page);
  if (!section) return;
  section.classList.remove('hidden');
  document.querySelectorAll('.nav-link').forEach(link => {
    const selected = link.dataset.view === page;
    link.classList.toggle('active', selected);
    if (selected) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  const navLink = document.querySelector(`.nav-link[data-view="${page}"] span:nth-child(2)`);
  $('currentSection').textContent = navLink ? navLink.textContent.trim() : ({
    'auth-page': 'Account access'
  }[page] || 'Dashboard');
  toggleSidebar(false);
  if (page === 'dashboard') renderDashboard();
  if (page === 'tutors-page') loadTutors();
  if (page === 'bookings-page') renderBookings();
  if (page === 'calendar-page') loadCalendar();
  if (page === 'profile-page') renderProfile();
  if (page === 'settings-page') renderSettings();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function toggleAuth(isRegistering) {
  registering = isRegistering;
  document.querySelectorAll('.regonly').forEach(element => {
    element.classList.toggle('hidden', !registering);
  });
  $('authTitle').textContent = registering ? 'Create your account' : 'Welcome back';
  $('authSubmit').textContent = registering ? 'Create account' : 'Log in';
  $('loginTab').classList.toggle('active', !registering);
  $('registerTab').classList.toggle('active', registering);
  $('password').autocomplete = registering ? 'new-password' : 'current-password';
  roleFields();
}

function roleFields() {
  const isTutor = registering && $('role').value === 'tutor';
  $('tutorFields').classList.toggle('hidden', !isTutor);
  $('subject').required = isTutor;
}

async function submitAuth(event) {
  event.preventDefault();
  try {
    if (registering) {
      await api('/register', 'POST', {
        name: $('name').value,
        email: $('email').value,
        password: $('password').value,
        role: $('role').value,
        subject: $('subject').value,
        specialties: $('specialties').value || $('subject').value,
        bio: $('bio').value
      });
      msg('Account created. Please log in.');
      $('authForm').reset();
      toggleAuth(false);
      return;
    }
    const result = await api('/login', 'POST', {
      email: $('email').value,
      password: $('password').value
    });
    token = result.token;
    user = result.user;
    sessionStorage.setItem('tc_token', token);
    updateSessionUi();
    msg('Welcome, ' + user.name + '!');
    show('dashboard');
  } catch (error) {
    msg(error.message, true);
  }
}

function updateSessionUi() {
  const account = $('sidebarAccount');
  $('topUser').innerHTML = user
    ? `<img src="${escapeHtml(user.avatar)}" alt=""><span>${escapeHtml(user.name.split(' ')[0])}</span>`
    : '<span class="user-dot">?</span><span>Log in</span>';
  account.innerHTML = user
    ? `<img src="${escapeHtml(user.avatar)}" alt=""><span class="account-copy"><strong>${escapeHtml(user.name)}</strong><small>${escapeHtml(user.role)}</small></span><button class="account-logout" onclick="logout()" aria-label="Log out">↗</button>`
    : '<div class="account-copy"><strong>Welcome to TutorConnect</strong><small>Sign in to book a session</small></div><button class="account-login" onclick="show(\'auth-page\')">Log in</button>';
  $('settingsAuth').textContent = user ? 'Log out' : 'Log in';
  $('settingsAuth').onclick = user ? logout : () => show('auth-page');
  $('sessionSetting').textContent = user
    ? 'Signed in as ' + user.email
    : 'Sign in to manage your tutoring account.';
}

async function loadTutors() {
  const search = $('search');
  if (!search) return;
  const requestId = ++tutorRequestId;
  try {
    const params = new URLSearchParams({
      q: search.value.trim(),
      module: $('moduleFilter').value,
      available: $('availableOnly').checked ? '1' : ''
    });
    const result = await api('/tutors?' + params.toString());
    if (requestId !== tutorRequestId) return;
    if (result.modules.join('|') !== moduleOptions.join('|')) {
      moduleOptions = result.modules;
      populateModuleFilters();
    }
    $('tutorNavCount').textContent = result.tutors.length;
    $('tutorResultsCount').textContent = result.tutors.length + (result.tutors.length === 1 ? ' tutor' : ' tutors');
    $('tutorResultsLabel').textContent = result.tutors.length ? 'Peer tutors for your next study session' : 'No tutors match those filters';
    $('tutors').innerHTML = result.tutors.length
      ? result.tutors.map(tutorCard).join('')
      : '<div class="empty-state"><span class="empty-icon">⌕</span><h3>No tutors found</h3><p>Try another name, module or availability filter.</p><button class="button button-soft" onclick="clearTutorFilters()">Clear filters</button></div>';
  } catch (error) {
    if (requestId === tutorRequestId) msg(error.message, true);
  }
}

function populateModuleFilters() {
  const options = moduleOptions.map(module =>
    `<option value="${escapeHtml(module)}">${escapeHtml(module)}</option>`
  ).join('');
  const filter = $('moduleFilter');
  const selected = filter.value || localStorage.getItem('tc_preferred_module') || '';
  filter.innerHTML = '<option value="">All modules</option>' + options;
  if ([...filter.options].some(option => option.value === selected)) filter.value = selected;
  const preferred = $('preferredModule');
  if (preferred) {
    const current = localStorage.getItem('tc_preferred_module') || '';
    preferred.innerHTML = '<option value="">No preference</option>' + options;
    preferred.value = [...preferred.options].some(option => option.value === current) ? current : '';
  }
}

function tutorCard(tutor) {
  const count = Number(tutor.learner_count);
  const capacity = Number(tutor.capacity);
  const full = Boolean(tutor.fully_booked);
  const modules = String(tutor.specialties || tutor.subject).split(',').map(value => value.trim()).filter(Boolean);
  const next = tutor.next_available ? formatDate(tutor.next_available, { weekday: 'short', month: 'short', day: 'numeric' }) : 'No slots yet';
  return `<article class="tutor-card">
    <div class="tutor-card-top"><img class="tutor-avatar" src="${escapeHtml(tutor.avatar)}" alt="Illustrated tutor portrait for ${escapeHtml(tutor.name)}" loading="lazy"><span class="availability-pill ${full || !tutor.available_slots ? 'unavailable' : ''}"><i></i>${full ? 'Fully booked' : tutor.available_slots ? 'Available' : 'No open slots'}</span></div>
    <h3>${escapeHtml(tutor.name)}</h3><p class="tutor-subtitle">${escapeHtml(tutor.subject)} tutor</p>
    <p class="tutor-bio">${escapeHtml(tutor.bio)}</p>
    <div class="specialty-list">${modules.map(module => `<span class="specialty">${escapeHtml(module)}</span>`).join('')}</div>
    <div class="capacity-block"><div class="capacity-heading"><strong>${count}/${capacity} Learners</strong><span>${full ? 'Fully Booked' : `${capacity - count} Space${capacity - count === 1 ? '' : 's'} Remaining`}</span></div>
      <div class="progress-track" role="progressbar" aria-label="${escapeHtml(tutor.name)} learner capacity" aria-valuenow="${count}" aria-valuemin="0" aria-valuemax="${capacity}"><span style="width:${Math.min(100, count / capacity * 100)}%"></span></div>
    </div>
    <div class="tutor-card-foot"><span><small>Next available</small><strong>${escapeHtml(next)}</strong></span><span class="slot-count">${Number(tutor.available_slots)} open slots</span></div>
    <button class="button ${full ? 'button-disabled' : 'button-soft'} tutor-action" ${full ? 'disabled' : ''} onclick="openTutor(${Number(tutor.id)})">${full ? 'Fully booked' : 'View availability'} <span aria-hidden="true">→</span></button>
    <div class="slot-list" id="slots-${Number(tutor.id)}"></div>
  </article>`;
}

async function clearTutorFilters() {
  $('search').value = '';
  $('moduleFilter').value = '';
  $('availableOnly').checked = false;
  return loadTutors();
}

async function openTutor(id) {
  const container = $('slots-' + id);
  if (container.innerHTML) {
    container.innerHTML = '';
    return;
  }
  try {
    const result = await api('/slots?tutor=' + encodeURIComponent(id));
    const capacity = `<div class="slot-capacity"><strong>${result.learner_count}/${result.capacity} learners</strong><span>${result.spaces_remaining} spaces remaining</span></div>`;
    const slots = result.slots.length
      ? result.slots.map(slot => `<div class="slot-row"><span>${escapeHtml(formatDate(slot.start, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }))}</span><button class="button button-primary button-small" onclick="book(${Number(slot.id)})">Book</button></div>`).join('')
      : `<p class="slot-empty">${result.fully_booked ? 'This tutor has reached the five-learner limit.' : 'No future time slots are available right now.'}</p>`;
    container.innerHTML = `<div class="slot-panel"><h4>Upcoming availability</h4>${capacity}${slots}</div>`;
  } catch (error) {
    msg(error.message, true);
  }
}

async function book(id) {
  if (!user) {
    msg('Log in as a student to book a session.');
    show('auth-page');
    return;
  }
  if (user.role !== 'student') {
    msg('Only student accounts can book tutoring sessions.', true);
    return;
  }
  try {
    const result = await api('/bookings', 'POST', { slot_id: id });
    msg(result.message);
    show('dashboard');
  } catch (error) {
    msg(error.message, true);
    loadTutors();
  }
}

function statCard(icon, label, value, hint, progress) {
  const meter = progress === undefined ? '' : `<div class="progress-track stat-progress"><span style="width:${Math.min(100, progress)}%"></span></div>`;
  return `<article class="stat-card"><div class="stat-card-head"><span class="stat-icon">${icon}</span><span class="stat-kicker">${escapeHtml(label)}</span></div><strong class="stat-value">${escapeHtml(value)}</strong><span class="stat-hint">${escapeHtml(hint)}</span>${meter}</article>`;
}

async function renderDashboard() {
  if (!user) {
    $('welcome').textContent = 'Welcome to TutorConnect';
    $('roleDescription').textContent = 'Your next step starts with a great tutor.';
    $('dashboardStats').innerHTML = '';
    $('dashboardContent').innerHTML = `<div class="guest-welcome"><div><span class="eyebrow">START LEARNING WITH CONFIDENCE</span><h2>Find the support you need to succeed.</h2><p>Browse peer tutors across popular university modules, compare upcoming availability and book a session in a few clicks.</p><button class="button button-primary" onclick="show('tutors-page')">Explore peer tutors <span aria-hidden="true">→</span></button></div><div class="guest-art"><span>✦</span><small>Learn together</small></div></div><div class="section-title-row"><div><div class="eyebrow">A GREAT PLACE TO START</div><h2>Popular peer tutors</h2></div><button class="text-link" onclick="show('tutors-page')">View all tutors →</button></div><div id="dashboardTutors" class="tutor-grid compact-grid"></div>`;
    try {
      const result = await api('/tutors');
      $('tutorNavCount').textContent = result.tutors.length;
      $('dashboardTutors').innerHTML = result.tutors.slice(0, 3).map(tutorCard).join('');
      if (result.modules.join('|') !== moduleOptions.join('|')) {
        moduleOptions = result.modules;
        populateModuleFilters();
      }
    } catch (error) {
      msg(error.message, true);
    }
    return;
  }

  $('welcome').textContent = 'Good to see you, ' + user.name.split(' ')[0];
  $('roleDescription').textContent = ({
    student: 'Your next study session is just around the corner.',
    tutor: 'Share what you know and help another learner progress.',
    admin: 'Here is the latest overview of the TutorConnect community.'
  })[user.role];
  try {
    const stats = await api('/stats');
    if (user.role === 'student') {
      $('dashboardStats').innerHTML = [
        statCard('⌕', 'Available tutors', stats.available_tutors, 'Ready to help you learn'),
        statCard('▦', 'Upcoming sessions', stats.upcoming_sessions, 'Keep your learning on track'),
        statCard('▤', 'My bookings', stats.active_bookings, 'Confirmed tutoring sessions'),
        statCard('✓', 'Booking history', stats.booking_history, 'Past and cancelled sessions')
      ].join('');
      const bookings = await api('/bookings');
      const upcoming = bookings.bookings.filter(booking => booking.status === 'confirmed' && !booking.completed).slice(0, 4);
      $('dashboardContent').innerHTML = `<div class="section-title-row"><div><div class="eyebrow">YOUR SCHEDULE</div><h2>Upcoming sessions</h2></div><button class="text-link" onclick="show('bookings-page')">View all bookings →</button></div>${bookingList(upcoming, 'No upcoming sessions. Find a tutor to book your first session.')}`;
    } else if (user.role === 'tutor') {
      const percent = stats.capacity ? stats.active_learners / stats.capacity * 100 : 0;
      $('dashboardStats').innerHTML = [
        statCard('◉', 'Active learners', `${stats.active_learners}/${stats.capacity}`, `${stats.spaces_remaining} learner spaces remaining`, percent),
        statCard('▦', 'Upcoming sessions', stats.upcoming_sessions, 'Confirmed learner sessions'),
        statCard('＋', 'Available time slots', stats.available_slots, 'Open for new bookings'),
        statCard('▤', 'Assigned modules', stats.assigned_modules.length, 'Subjects on your profile')
      ].join('');
      const [bookings, slots] = await Promise.all([api('/bookings'), api('/my-slots')]);
      const upcoming = bookings.bookings.filter(booking => booking.status === 'confirmed' && !booking.completed).slice(0, 4);
      const openSlots = slots.slots.filter(slot => slot.status === 'Available').slice(0, 5);
      $('dashboardContent').innerHTML = `<div class="dashboard-columns"><section><div class="section-title-row"><div><div class="eyebrow">YOUR SESSIONS</div><h2>Upcoming tutoring</h2></div><button class="text-link" onclick="show('bookings-page')">View all →</button></div>${bookingList(upcoming, 'No upcoming sessions yet.')}</section><section><div class="section-title-row"><div><div class="eyebrow">YOUR AVAILABILITY</div><h2>Open time slots</h2></div><button class="text-link" onclick="show('calendar-page')">Calendar →</button></div>${slotManagement(slots.slots, openSlots)}</section></div>`;
    } else {
      const capacities = stats.tutor_capacities || [];
      $('dashboardStats').innerHTML = [
        statCard('♙', 'Registered students', stats.registered_students, 'Active student accounts'),
        statCard('◉', 'Registered tutors', stats.registered_tutors, 'Verified tutor accounts'),
        statCard('▤', 'All bookings', stats.all_bookings, 'Across the platform'),
        statCard('!', 'Fully booked tutors', stats.full_capacity_tutors, 'At the five-learner limit')
      ].join('');
      const capacityRows = capacities.map(tutor => `<div class="capacity-row"><img src="${escapeHtml('/avatars/' + tutor.id + '.svg')}" alt=""><span><strong>${escapeHtml(tutor.name)}</strong><small>${escapeHtml(tutor.subject)}${tutor.is_demo ? ' · Demo profile' : ''}</small></span><span class="capacity-number">${tutor.learner_count}/${tutor.capacity}</span><div class="progress-track"><span style="width:${tutor.learner_count / tutor.capacity * 100}%"></span></div></div>`).join('');
      const users = await api('/admin/users');
      $('dashboardContent').innerHTML = `<div class="section-title-row"><div><div class="eyebrow">PLATFORM OVERVIEW</div><h2>Tutor capacity overview</h2></div><button class="text-link" onclick="show('bookings-page')">Review bookings →</button></div><div class="admin-grid"><section class="panel-card"><h3>Registered and demonstration tutors</h3>${capacityRows || '<div class="empty-inline">No tutors registered yet.</div>'}</section><section class="panel-card"><h3>Recent users <span class="muted-count">${users.users.length}</span></h3><div class="user-list">${users.users.slice(0, 7).map(item => `<div class="user-row"><img src="${escapeHtml('/avatars/' + item.id + '.svg')}" alt=""><span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.email)}</small></span><span class="role-badge">${item.is_demo ? 'Demo tutor' : escapeHtml(item.role)}</span></div>`).join('')}</div></section></div>`;
    }
  } catch (error) {
    msg(error.message, true);
  }
}

function bookingList(bookings, emptyMessage) {
  if (!bookings.length) return `<div class="empty-inline">${escapeHtml(emptyMessage)} <button class="text-link" onclick="show('tutors-page')">Browse tutors →</button></div>`;
  return `<div class="booking-list">${bookings.map(booking => `<article class="booking-row"><span class="date-tile"><strong>${escapeHtml(new Date(booking.start).toLocaleDateString(undefined, { day: '2-digit' }))}</strong><small>${escapeHtml(new Date(booking.start).toLocaleDateString(undefined, { month: 'short' }))}</small></span><span class="booking-info"><strong>${escapeHtml(booking.tutor || booking.student)}</strong><small>${escapeHtml(booking.subject || 'Tutoring session')} · ${escapeHtml(formatDate(booking.start, { hour: 'numeric', minute: '2-digit' }))}</small></span><span class="status-pill">${escapeHtml(booking.status)}</span></article>`).join('')}</div>`;
}

function slotManagement(allSlots, openSlots) {
  return `<div class="panel-card availability-card"><label for="newslot">Add available tutoring time</label><div class="slot-add"><input id="newslot" type="datetime-local"><button class="button button-primary button-small" onclick="addSlot()">Add time</button></div><div class="mini-slot-list">${openSlots.map(slot => `<div><span>${escapeHtml(formatDate(slot.start, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }))}</span><span class="availability-pill"><i></i>Open</span></div>`).join('') || '<p class="empty-inline">No open time slots. Add your availability above.</p>'}</div><span class="sr-only">${allSlots.length} total slots</span></div>`;
}

function setBookingFilter(filter) {
  bookingFilter = filter;
  document.querySelectorAll('[data-booking-filter]').forEach(tab => tab.classList.toggle('active', tab.dataset.bookingFilter === filter));
  renderBookings();
}

async function renderBookings() {
  if (!user) {
    $('bookingsContent').innerHTML = `<div class="empty-state"><h3>Log in to see your bookings</h3><p>Your upcoming sessions and booking history will appear here.</p><button class="button button-primary" onclick="show('auth-page')">Log in</button></div>`;
    return;
  }
  try {
    const result = await api('/bookings');
    let bookings = result.bookings;
    if (bookingFilter === 'upcoming') bookings = bookings.filter(booking => booking.status === 'confirmed' && !booking.completed);
    if (bookingFilter === 'history') bookings = bookings.filter(booking => booking.status !== 'confirmed' || booking.completed);
    $('bookingsContent').innerHTML = bookings.length
      ? `<div class="booking-table-wrap"><table class="booking-table"><thead><tr><th>Session</th><th>${user.role === 'student' ? 'Tutor' : user.role === 'tutor' ? 'Learner' : 'Tutor / learner'}</th><th>Module</th><th>Status</th><th>Action</th></tr></thead><tbody>${bookings.map(booking => `<tr><td><strong>${escapeHtml(formatDate(booking.start, { weekday: 'short', month: 'short', day: 'numeric' }))}</strong><small>${escapeHtml(formatDate(booking.start, { hour: 'numeric', minute: '2-digit' }))}</small></td><td>${escapeHtml(user.role === 'admin' ? `${booking.tutor} / ${booking.student}` : booking.tutor || booking.student)}</td><td>${escapeHtml(booking.subject || 'Tutoring')}</td><td><span class="status-pill ${booking.status === 'cancelled' ? 'cancelled' : booking.completed ? 'completed' : ''}">${booking.completed && booking.status === 'confirmed' ? 'Completed' : escapeHtml(booking.status)}</span></td><td>${booking.status === 'confirmed' && !booking.completed && user.role !== 'admin' ? `<button class="button button-quiet button-small" onclick="cancelBooking(${Number(booking.id)})">Cancel</button>` : '—'}</td></tr>`).join('')}</tbody></table></div>`
      : `<div class="empty-state"><span class="empty-icon">▤</span><h3>${bookingFilter === 'history' ? 'No booking history yet' : 'Nothing scheduled yet'}</h3><p>${bookingFilter === 'history' ? 'Past and cancelled sessions will be saved here.' : 'Book a session with a peer tutor to get started.'}</p>${bookingFilter !== 'history' && user.role === 'student' ? '<button class="button button-primary" onclick="show(\'tutors-page\')">Find a tutor</button>' : ''}</div>`;
  } catch (error) {
    msg(error.message, true);
  }
}

async function addSlot() {
  try {
    const result = await api('/slots', 'POST', { start: $('newslot').value });
    msg(result.message);
    renderDashboard();
  } catch (error) {
    msg(error.message, true);
  }
}

async function cancelBooking(id) {
  if (!window.confirm('Cancel this tutoring session?')) return;
  try {
    const result = await api('/cancel', 'POST', { id });
    msg(result.message + ' Learner capacity has been updated.');
    renderBookings();
    renderDashboard();
  } catch (error) {
    msg(error.message, true);
  }
}

function moveCalendar(amount) {
  calendarOffset += amount;
  loadCalendar();
}

async function loadCalendar() {
  try {
    const result = await api('/calendar');
    calendarEvents = result.events;
    renderCalendar();
  } catch (error) {
    msg(error.message, true);
  }
}

function renderCalendar() {
  const today = new Date();
  const monday = new Date(today);
  monday.setHours(0, 0, 0, 0);
  monday.setDate(monday.getDate() - (monday.getDay() + 6) % 7 + calendarOffset * 7);
  const sunday = new Date(monday);
  sunday.setDate(sunday.getDate() + 6);
  $('calendarTitle').textContent = calendarOffset === 0
    ? 'This week'
    : `${monday.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} – ${sunday.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
  const weekday = new Intl.DateTimeFormat(undefined, { weekday: 'short' });
  const dayNumber = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' });
  $('calendarGrid').innerHTML = Array.from({ length: 7 }, (_, index) => {
    const day = new Date(monday);
    day.setDate(monday.getDate() + index);
    const dayEvents = calendarEvents.filter(event => sameDay(new Date(event.start), day));
    return `<section class="calendar-day ${sameDay(day, today) ? 'today' : ''}"><div class="calendar-day-head"><span>${weekday.format(day)}</span><strong>${day.getDate()}</strong><small>${dayNumber.format(day)}</small></div><div class="calendar-day-events">${dayEvents.length ? dayEvents.map(event => `<button class="calendar-event ${event.available ? 'event-available' : 'event-booked'}" ${event.available ? `onclick="book(${Number(event.id)})"` : 'disabled'}><strong>${escapeHtml(formatDate(event.start, { hour: 'numeric', minute: '2-digit' }))}</strong><span>${escapeHtml(event.available ? event.tutor : event.student || event.tutor)}</span><small>${escapeHtml(event.available ? event.subject : 'Booked session')}</small></button>`).join('') : '<span class="no-events">—</span>'}</div></section>`;
  }).join('');
}

function sameDay(first, second) {
  return first.getFullYear() === second.getFullYear() && first.getMonth() === second.getMonth() && first.getDate() === second.getDate();
}

function formatDate(value, options) {
  return new Date(value).toLocaleString(undefined, options);
}

function renderProfile() {
  $('profileContent').innerHTML = user
    ? `<div class="profile-card"><img class="profile-avatar" src="${escapeHtml(user.avatar)}" alt="Profile avatar"><div class="profile-main"><div class="eyebrow">${escapeHtml(user.role)} ACCOUNT</div><h2>${escapeHtml(user.name)}</h2><p>${escapeHtml(user.email)}</p>${user.role === 'tutor' ? `<div class="specialty-list">${String(user.specialties || user.subject).split(',').map(module => `<span class="specialty">${escapeHtml(module.trim())}</span>`).join('')}</div><p class="profile-bio">${escapeHtml(user.bio || 'Add a little introduction when you are ready.')}</p><div class="profile-capacity"><strong>${user.learner_count}/${user.capacity} Learners</strong><span>${user.spaces_remaining} Spaces Remaining</span><div class="progress-track"><span style="width:${user.learner_count / user.capacity * 100}%"></span></div></div>` : '<p class="profile-bio">Your learner account is ready. Explore modules and book your next tutoring session.</p>'}</div><button class="button button-quiet" onclick="logout()">Log out</button></div>`
    : `<div class="empty-state"><h3>Your profile is waiting</h3><p>Log in or register to manage your TutorConnect account.</p><button class="button button-primary" onclick="show('auth-page')">Log in or sign up</button></div>`;
}

function renderSettings() {
  const preferred = $('preferredModule');
  if (preferred && moduleOptions.length && preferred.options.length <= 1) populateModuleFilters();
  $('reduceMotion').checked = localStorage.getItem('tc_reduce_motion') === 'true';
  $('installButton').classList.toggle('hidden', !installPrompt);
  updateSessionUi();
}

function authAction() {
  if (user) logout();
  else show('auth-page');
}

async function logout() {
  try {
    if (token) await api('/logout', 'POST', {});
  } catch (error) {
    msg(error.message, true);
  } finally {
    token = '';
    user = null;
    sessionStorage.removeItem('tc_token');
    updateSessionUi();
    msg('You have been logged out.');
    show('dashboard');
  }
}

async function installApp() {
  if (!installPrompt) return;
  installPrompt.prompt();
  await installPrompt.userChoice;
  installPrompt = null;
  $('installButton').classList.add('hidden');
}

function setupPreferences() {
  $('preferredModule').addEventListener('change', event => {
    localStorage.setItem('tc_preferred_module', event.target.value);
    $('moduleFilter').value = event.target.value;
  });
  $('reduceMotion').addEventListener('change', event => {
    localStorage.setItem('tc_reduce_motion', String(event.target.checked));
    document.documentElement.classList.toggle('reduce-motion', event.target.checked);
  });
  $('search').addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadTutors, 180);
  });
  $('moduleFilter').addEventListener('change', loadTutors);
  $('availableOnly').addEventListener('change', loadTutors);
  $('search').addEventListener('keydown', event => {
    if (event.key === 'Enter') loadTutors();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') toggleSidebar(false);
  });
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    installPrompt = event;
    if (!$('settings-page').classList.contains('hidden')) $('installButton').classList.remove('hidden');
  });
  window.addEventListener('appinstalled', () => {
    installPrompt = null;
    $('installButton').classList.add('hidden');
    msg('TutorConnect has been installed.');
  });
}

async function init() {
  setupPreferences();
  if (localStorage.getItem('tc_reduce_motion') === 'true') document.documentElement.classList.add('reduce-motion');
  updateSessionUi();
  try {
    const tutors = await api('/tutors');
    moduleOptions = tutors.modules;
    populateModuleFilters();
    $('tutorNavCount').textContent = tutors.tutors.length;
  } catch (error) {
    msg(error.message, true);
  }
  if (token) {
    try {
      user = (await api('/me')).user;
      if (!user) {
        token = '';
        sessionStorage.removeItem('tc_token');
      }
    } catch (error) {
      token = '';
      sessionStorage.removeItem('tc_token');
      msg(error.message, true);
    }
  }
  updateSessionUi();
  $('todayLabel').textContent = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).toUpperCase();
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(error => console.error('Service worker registration failed:', error));
  }
  show('dashboard');
}

init();
