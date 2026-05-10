from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

# def landing_page(request):
#     """Beautiful landing page for guest users"""
#     if request.user.is_authenticated:
#         return redirect('admin:index')
    
#     context = {
#         'title': 'Admin Portal - Modern Management Solution',
#         'description': 'Streamline your business operations with our powerful admin dashboard',
#     }
#     return render(request, 'guest_portal/landing.html', context)


def landing_page(request):
    """UFAA landing page for guest users"""
    if request.user.is_authenticated:
        # If user is logged in as staff, redirect to admin dashboard
        if request.user.is_staff:
            from django.shortcuts import redirect
            return redirect('admin:index')
    
    context = {
        'title': 'UFAA Kenya - Reuniting You with Your Unclaimed Financial Assets',
        'description': 'Search and claim your unclaimed financial assets including bank accounts, SACCOS, insurance policies, pensions, and more.',
        'site_name': 'UFAA Kenya',
        'year': 2024,
    }
    return render(request, 'guest_portal/landing.html', context)



@staff_member_required
def admin_dashboard(request):
    """Admin dashboard for authenticated staff users"""
    # Get statistics for the dashboard
    total_users = User.objects.count()
    active_users = User.objects.filter(
        last_login__gte=timezone.now() - timedelta(days=30)
    ).count()
    new_users_today = User.objects.filter(
        date_joined__date=timezone.now().date()
    ).count()
    new_users_week = User.objects.filter(
        date_joined__gte=timezone.now() - timedelta(days=7)
    ).count()
    
    # Get recent users
    recent_users = User.objects.order_by('-date_joined')[:5]
    
    context = {
        'title': 'Admin Dashboard',
        'total_users': total_users,
        'active_users': active_users,
        'new_users_today': new_users_today,
        'new_users_week': new_users_week,
        'recent_users': recent_users,
        'current_time': timezone.now(),
    }
    return render(request, 'guest_portal/admin_dashboard.html', context)

def contact_submit(request):
    """Handle contact form submission"""
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')
        
        # Validate form data
        if not name or not email or not message:
            messages.error(request, 'Please fill in all fields.')
            return redirect('guest_portal:landing')
        
        # Send email notification (optional)
        try:
            send_mail(
                f'Contact Form Submission from {name}',
                f'From: {name} ({email})\n\nMessage:\n{message}',
                settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'webmaster@localhost',
                [settings.ADMIN_EMAIL] if hasattr(settings, 'ADMIN_EMAIL') else ['admin@example.com'],
                fail_silently=False,
            )
            messages.success(request, 'Thank you for your message! We\'ll get back to you soon.')
        except Exception as e:
            # Log the error if needed
            messages.warning(request, 'Message received. We will contact you shortly.')
        
        return redirect('guest_portal:landing')
    
    return redirect('guest_portal:landing')