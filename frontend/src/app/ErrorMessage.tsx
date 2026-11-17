import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

export function ErrorMessage({ message }: { message: string }) {
  const { t } = useTranslation()
  return (
    <section role="alert" className="mx-auto mt-16 max-w-md text-center">
      <p className="mb-4">{message}</p>
      <Link className="text-primary underline underline-offset-4" to="/">
        {t('errors.backHome')}
      </Link>
    </section>
  )
}
