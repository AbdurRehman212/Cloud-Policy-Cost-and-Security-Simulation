/**
 * Page Object for the /login route.
 *
 * Selectors are role-based + accessible-name driven. The form lacks
 * data-testid attributes, but inputs have associated <label> text and the
 * submit button has a stable visible name "Sign In" / "Signing in...".
 */
import { Page, Locator, expect } from '@playwright/test';

export class LoginPage {
  readonly page: Page;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly heading: Locator;

  constructor(page: Page) {
    this.page = page;
    // The <label> contains "Email Address" — the input's placeholder is
    // "you@example.com". Two robust anchors:
    this.emailInput = page.getByPlaceholder(/you@example\.com/i);
    this.passwordInput = page.getByPlaceholder(/•+/);
    this.submitButton = page.getByRole('button', { name: /^sign in$|signing in/i });
    this.heading = page.getByRole('heading', {
      name: /cloud policy.*simulator/i,
    });
  }

  async goto(): Promise<void> {
    await this.page.goto('/login');
    await expect(this.heading).toBeVisible();
  }

  async login(email: string, password: string): Promise<void> {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.submitButton.click();
    // Successful login navigates away from /login.
    await this.page.waitForURL((url) => !url.pathname.startsWith('/login'), {
      timeout: 15_000,
    });
  }
}
