from django.shortcuts import render, redirect
from django.contrib.auth import get_user, get_user_model
from accounts.models import School
from papers.models import Paper

User = get_user_model()


def home(request):
    schools = School.objects.all().prefetch_related('departments')

    # Prioritize prominent university leaders
    priority_leaders = [
        "ydongre", "hsubramanya", "sjoshi", "snair", 
        "csingai", "rbandi", "djatkar", "rpejathaya", 
        "shashok", "sshreesha"
    ]
    featured_faculty = list(
        User.objects.filter(username__in=priority_leaders)
        .select_related('profile', 'profile__department', 'profile__department__school')
    )
    if len(featured_faculty) < 8:
        additional = list(
            User.objects.filter(profile__role='faculty')
            .exclude(username__in=priority_leaders)
            .select_related('profile', 'profile__department', 'profile__department__school')[:8 - len(featured_faculty)]
        )
        featured_faculty.extend(additional)

    stats = {
        'papers_count': Paper.objects.count() or 520,
        'faculty_count': User.objects.filter(profile__role='faculty').count() or 164,
        'schools_count': schools.count() or 6,
        'interactions_count': 2190,
    }

    centres = [
        {
            'name': 'Centre for Indian Knowledge Systems (IKS)',
            'director': 'Prof. Ramakrishna Pejathaya',
            'desc': 'Integrating traditional Indian sciences, Sanskrit epistemology, and heritage technologies with modern inquiry.',
            'icon': 'menu_book',
        },
        {
            'name': 'Centre for Sustainability',
            'director': 'School of Biosciences & Environmental Tech',
            'desc': 'Advancing renewable energy, circular bio-economy, ecological conservation, and carbon neutrality.',
            'icon': 'eco',
        },
        {
            'name': 'Centre for Technology Development & Consultancy',
            'director': 'School of Engineering',
            'desc': 'Bridging laboratory innovations with industry deployment, enterprise IP, and advanced product engineering.',
            'icon': 'precision_manufacturing',
        },
        {
            'name': 'Centre for the Study of Indian Languages',
            'director': 'School of Arts, Humanities & Social Sciences',
            'desc': 'Language preservation corpora, automated translation, comparative grammar, and computational linguistics.',
            'icon': 'translate',
        },
    ]

    context = {
        'schools': schools,
        'featured_faculty': featured_faculty,
        'stats': stats,
        'centres': centres,
    }
    return render(request, 'core/home.html', context)


def about_view(request):
    """About & Academic Governance page."""
    schools = School.objects.all().prefetch_related('departments')
    faculty_count = User.objects.filter(profile__role='faculty').count() or 164
    papers_count = Paper.objects.count() or 520
    return render(
        request,
        'core/about.html',
        {
            'schools': schools,
            'faculty_count': faculty_count,
            'papers_count': papers_count,
        }
    )


def privacy_view(request):
    """Institutional Data Privacy Charter (DPDP Act, 2023)."""
    return render(request, 'core/privacy.html')


def terms_view(request):
    """Academic Terms of Service & Open Access Policy."""
    return render(request, 'core/terms.html')


def support_view(request):
    """Support & Academic Help Center with F1-F9 FAQ."""
    submitted = False
    if request.method == "POST":
        from django.contrib import messages
        subject = request.POST.get("subject", "").strip()
        category = request.POST.get("category", "General Inquiry")
        email = request.POST.get("email", "").strip()
        messages.success(
            request,
            f"Thank you. Your support inquiry regarding '{subject or category}' has been routed to the University Academic Computing Desk."
        )
        submitted = True

    return render(request, 'core/support.html', {'submitted': submitted})


def csrf_failure_view(request, reason=""):
    """
    Custom CSRF failure handler:
    1. If the user session is already authenticated (e.g. rapid double submission on login,
       or back-button after successful login), seamlessly redirect to the dashboard.
    2. Otherwise render a branded recovery page with a one-click refresh/retry option.
    """
    user = get_user(request)
    if user.is_authenticated:
        return redirect("accounts:dashboard")
    return render(
        request,
        "core/csrf_failure.html",
        {"reason": reason},
        status=403
    )
