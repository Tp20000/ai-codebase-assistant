import sys, asyncio
sys.path.insert(0, 'backend')
import warnings
warnings.filterwarnings('ignore')

async def test():
    from app.database import AsyncSessionLocal
    from app.repositories.user_repo import UserRepository
    from app.utils.password import hash_password
    from app.models.user import User
    import uuid

    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)
        test_email = f'direct_{uuid.uuid4().hex[:6]}@test.com'
        test_username = f'direct_{uuid.uuid4().hex[:6]}'

        # Check email doesn't exist
        exists = await repo.email_exists(test_email)
        print(f'email_exists check: {exists}')

        # Create user
        user = User(
            email=test_email,
            username=test_username,
            hashed_password=hash_password('TestPassword123!'),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f'User created: id={user.id}, email={user.email}')
        print(f'  preferred_model={user.preferred_model}')
        print(f'  theme={user.theme}')
        print(f'  is_active={user.is_active}')

        # Cleanup
        await db.delete(user)
        await db.commit()
        print('Cleanup done')
        return True

try:
    result = asyncio.run(test())
    print()
    print('DIRECT DB TEST: PASSED')
except Exception as e:
    import traceback
    traceback.print_exc()
    print()
    print(f'DIRECT DB TEST: FAILED - {e}')
