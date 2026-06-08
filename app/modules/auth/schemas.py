"""
Marshmallow schemas for auth request validation.
All schemas strip and normalize input.
"""
from marshmallow import Schema, fields, validate, validates, ValidationError


class SignupSchema(Schema):
    email = fields.Email(required=True)
    mobile_no = fields.Str(required=True, validate=validate.Regexp(
        r"^[6-9]\d{9}$", error="Mobile must be a valid 10-digit Indian number starting with 6-9."
    ))
    password = fields.Str(required=True, validate=validate.Length(min=8))
    confirmpassword = fields.Str(required=True, data_key="confirmpassword")

    @validates("password")
    def validate_password_strength(self, value):
        import re
        pattern = r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[@$!%*#?&]).{8,}$"
        if not re.match(pattern, value):
            raise ValidationError(
                "Password must be at least 8 characters and contain uppercase, "
                "lowercase, digit, and a special character (@$!%*#?&)."
            )


class VerifyOtpSchema(Schema):
    email = fields.Email(required=True)
    otp = fields.Str(required=True, validate=validate.Length(equal=6))


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=1))


class RefreshTokenSchema(Schema):
    refresh_token = fields.Str(required=True, validate=validate.Length(min=10))


class ForgotPasswordSchema(Schema):
    email = fields.Email(required=True)


class ResetPasswordSchema(Schema):
    token = fields.Str(required=True, validate=validate.Length(min=10))
    new_password = fields.Str(required=True)
    confirm_password = fields.Str(required=True)

    @validates("new_password")
    def validate_password_strength(self, value):
        import re
        pattern = r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[@$!%*#?&]).{8,}$"
        if not re.match(pattern, value):
            raise ValidationError(
                "Password must be at least 8 characters and contain uppercase, "
                "lowercase, digit, and a special character (@$!%*#?&)."
            )


class ResendOtpSchema(Schema):
    email = fields.Email(required=True)
