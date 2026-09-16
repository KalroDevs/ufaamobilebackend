from .models import Claim

def get_next_claim_number():
    """Get the next claim number without creating a claim"""
    year = timezone.now().year
    last_claim = Claim.objects.filter(
        no__startswith=f'CM-{year}'
    ).order_by('-no').first()
    
    if last_claim and last_claim.no:
        parts = last_claim.no.split('-')
        if len(parts) == 3:
            try:
                last_num = int(parts[2])
                new_num = last_num + 1
            except ValueError:
                new_num = 1
        else:
            new_num = 1
    else:
        new_num = 1
    
    return f"CM-{year}-{new_num:05d}"

def validate_claim_number(claim_number):
    """Validate claim number format"""
    import re
    pattern = r'^CM-\d{4}-\d{5}$'
    return bool(re.match(pattern, claim_number))

def extract_year_from_claim_number(claim_number):
    """Extract year from claim number"""
    if validate_claim_number(claim_number):
        return int(claim_number.split('-')[1])
    return None