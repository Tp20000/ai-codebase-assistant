import sys, asyncio, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'backend')

async def test_register():
    from app.database import AsyncSessionLocal
    from app.repositories.user_repo import UserRepository
    from app.utils.password import hash_password
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)

        # Test attribute access
        print(f'  repo.db type: {type(repo.db).__name__}')

        # Test email_exists
        try:
            exists = await repo.email_exists('test@test.com')
            print(f'  email_exists works: {exists}')
        except Exception as e:
            print(f'  email_exists FAIL: {e}')
            return False

        # Test creating user
        try:
            import uuid
            from datetime import datetime, timezone
            user = User(
                email=f'testdirect_{uuid.uuid4().hex[:6]}@test.com',
                username=f'testdirect_{uuid.uuid4().hex[:6]}',
                hashed_password=hash_password('TestPassword123!'),
                is_active=True,
                is_verified=False,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f'  User created directly: id={user.id}')
            # Cleanup
            await db.delete(user)
            await db.commit()
            print(f'  Cleanup done')
            return True
        except Exception as e:
            await db.rollback()
            print(f'  User creation FAIL: {type(e).__name__}: {e}')
            return False

result = asyncio.run(test_register())
print()
print('REGISTER TEST: ' + ('PASSED' if result else 'FAILED'))
